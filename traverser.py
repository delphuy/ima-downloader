# traverser.py
# 统一知识库遍历收集器
# 负责递归遍历 IMA 分享，返回带正确 rel_path 的 KnowledgeFile 列表
# 供 GUI 和 CLI 共用，保证目录结构一致

import time
from pathlib import Path
from typing import Callable, Optional, Tuple, List

from api_service import ImaApiService
from downloader import (
    build_safe_filename,
    sanitize_name,
    get_content_type,
    resolve_item_download,
)
from models import KnowledgeFile


def collect_all_files(
    api: ImaApiService,
    share_id: str,
    on_folder: Optional[Callable[[Path, str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> Tuple[str, List[KnowledgeFile]]:
    """
    递归收集分享下的所有可下载文件，并构建正确的相对路径（不含根文件夹名）。
    返回:
        (root_name, [KnowledgeFile, ...])
    root_name 来自 current_path[0].name（用于创建本地根目录）
    """
    # 获取根目录名称
    resp = api.get_share_info(share_id=share_id, limit=20, cursor="", folder_id="")
    if resp.code != 0 or not resp.current_path:
        raise RuntimeError("获取目录失败")

    root_name = sanitize_name(resp.current_path[0].name)

    files: List[KnowledgeFile] = []
    _recurse_collect(
        api=api,
        share_id=share_id,
        folder_id="",
        current_rel=Path(""),
        files=files,
        on_folder=on_folder,
        cancel_check=cancel_check,
    )
    return root_name, files


def _recurse_collect(
    api: ImaApiService,
    share_id: str,
    folder_id: str,
    current_rel: Path,
    files: List[KnowledgeFile],
    on_folder: Optional[Callable[[Path, str], None]],
    cancel_check: Optional[Callable[[], bool]],
) -> None:
    """内部递归实现：按 folder_id 分页获取，构建 rel_path。"""
    cursor = ""
    while True:
        if cancel_check and cancel_check():
            return

        resp = api.get_share_info(
            share_id=share_id,
            limit=20,
            cursor=cursor,
            folder_id=folder_id,
        )
        if resp.code != 0:
            # 单个文件夹失败不影响整体
            break

        for item in resp.knowledge_list:
            if cancel_check and cancel_check():
                return

            if item.folder_info:
                # 子文件夹：用 name 构建路径并递归
                folder_name = sanitize_name(item.folder_info.name)
                new_rel = current_rel / folder_name
                if on_folder:
                    on_folder(new_rel, folder_name)
                _recurse_collect(
                    api=api,
                    share_id=share_id,
                    folder_id=item.folder_info.folder_id,
                    current_rel=new_rel,
                    files=files,
                    on_folder=on_folder,
                    cancel_check=cancel_check,
                )
            else:
                # 文件：附加当前相对路径（使用 build_safe_filename 确保带扩展名）
                # v1.0.4: 服务端已不再给匿名请求返回 jump_url（返回空）。
                # 旧逻辑 "if url and safe_name" 会把无 URL 条目静默丢弃，
                # 导致 "目录齐全但文件全空"。现在全量收集：
                #   - 有 jump_url  → source_kind=original
                #   - 无 jump_url  → cover_urls 推导（图片原件/首页预览）
                #   - 都没有      → source_kind=metadata
                # v1.0.5: 解析文本/摘要默认不落盘（下载层 save_texts 开关，默认关）
                url, kind = resolve_item_download(item)
                safe_name = build_safe_filename(
                    item.title,
                    item=item,
                    download_url=url,
                )
                if not safe_name:
                    safe_name = f"未命名条目_{len(files) + 1}"
                ctype = get_content_type(item.title, item.media_type_info)
                files.append(
                    KnowledgeFile(
                        url=url,
                        rel_path=current_rel / safe_name,
                        title=safe_name,
                        content_type=ctype,
                        source_kind=kind,
                        summary_text=item.introduction or "",
                        abstract_text=item.item_abstract or "",
                        media_id=item.media_id or "",
                        file_size=str(item.file_size or ""),
                        md5_sum=str(item.md5_sum or ""),
                        raw_file_url=item.raw_file_url or "",  # v1.0.7: 收割匹配备用键
                    )
                )

        if resp.is_end or not resp.next_cursor:
            break
        cursor = resp.next_cursor
        time.sleep(0.3)  # 保持原有礼貌延时


def collect_grouped_files(
    api: ImaApiService,
    share_id: str,
    on_folder: Optional[Callable[[Path, str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> Tuple[str, dict[str, List[KnowledgeFile]]]:
    """
    收集并按内容来源类型分组（链接类型/文档类型/文章类型）。
    返回:
        (root_name, {content_type: [KnowledgeFile, ...], ...})
    类型用于并行下载：同一类型文件在同一个线程内下载。
    """
    root_name, files = collect_all_files(
        api=api,
        share_id=share_id,
        on_folder=on_folder,
        cancel_check=cancel_check,
    )

    grouped: dict[str, List[KnowledgeFile]] = {}
    for kf in files:
        category = kf.content_type or "文章类型"
        if category not in grouped:
            grouped[category] = []
        grouped[category].append(kf)

    return root_name, grouped
