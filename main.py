
import os
import asyncio
import concurrent.futures
from pathlib import Path

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import File, Plain

from .core.api_client import ApiClient
import zipfile

@register(
    "astrbot_plugin_mmdDownload",
    "waterfeet",
    "mmd视频下载插件",
    "v1.0.0",
    "https://github.com/waterfeet/astrbot_plugin_mmdDownload",
)
class WaterFeetIwaraPlugin(Star):
    def __init__(self, context: Context, config):
        super().__init__(context)
        self.Iwara_account  = config.get("Iwara_account", "")
        self.Iwara_password = config.get("Iwara_password", "")
        self.Iwara_savepath = config.get("Iwara_savepath", "./downloads")
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=3)

    # -------------------------------------------------
    # 线程池任务：只做“下载+打包”，返回 zip 路径或异常
    # -------------------------------------------------
    def _download_and_zip(self, video_id: str) -> str:
        """
        返回打包后的 zip 路径；如有异常直接 raise
        """
        client = ApiClient(email=self.Iwara_account, password=self.Iwara_password)
        client.login()
        saved_path = client.download_video2(path=self.Iwara_savepath, video_id=video_id)
        if not saved_path or not os.path.isfile(saved_path):
            raise RuntimeError("下载失败或文件不存在")
        zip_path = self._pack_to_zip(saved_path)
        os.remove(saved_path)          # 清理原文件
        return zip_path

    # -------------------------------------------------
    # 工具：把单个文件打包成同名 zip
    # -------------------------------------------------
    @staticmethod
    def _pack_to_zip(src_path: str) -> str:
        src_path = os.path.abspath(src_path)
        if not os.path.isfile(src_path):
            raise FileNotFoundError(src_path)
        zip_path = os.path.splitext(src_path)[0] + ".zip"
        with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(src_path, arcname=os.path.basename(src_path))
        return zip_path

    # -------------------------------------------------
    # 指令入口：iwara <video_id>
    # -------------------------------------------------
    @filter.command("iwara")
    async def iwara_download(self, event: AstrMessageEvent, video_ID: str = None):
        """下载 Iwara 视频并打包发送"""
        if not (self.Iwara_account and self.Iwara_password):
            yield event.plain_result("未配置 Iwara 账号/密码，无法下载。")
            return
        if not video_ID:
            yield event.plain_result("请提供视频 ID，例如：iwara abc123")
            return

        # 立即返回“已开始”提示
        yield event.plain_result("已开始后台下载，完成后会主动推送。")
        event.stop_event()

        # 把耗时任务提交到线程池
        loop = asyncio.get_running_loop()
        try:
            zip_path = await loop.run_in_executor(self.pool, self._download_and_zip, video_ID)
            # 成功后主动推送
            yield event.chain_result([File(name=f"{video_ID}.zip", file=zip_path)])
            # 清理 zip 文件
            os.remove(zip_path)
        except Exception as e:
            logger.error(f"[Iwara] 后台任务失败: {e}")
            yield event.plain_result(f"Iwara 下载任务失败：{e}")


    # -------------------------------------------------
    # 把字节转成人类可读
    # -------------------------------------------------
    def pretty_size(self, num: int) -> str:
        if num < 1024:
            return f"{num}B"
        for unit in ["K", "M", "G"]:
            num /= 1024.0
            if num < 1024:
                return f"{num:.1f}{unit}"
        return f"{num:.1f}T"

    # -------------------------------------------------
    # 搜索指令：iwara.search [关键词] [页码] [每页条数]
    # -------------------------------------------------
    @filter.command("iwarapage")
    async def iwara_page(
        self,
        event: AstrMessageEvent,
        page: str = "0",
        limit: str = "5",
        date: str = ""
    ):
        """查看 Iwara 视频列表
        用法： iwarapage 页码 数量 年月
        iwarapage 0 10 2025-8
        iwarapage 0 5        # 不指定月份
        """
        try:
            page_int   = max(0, int(page))
            limit_int  = min(32, max(1, int(limit)))   # 服务端最大 32
        except ValueError:
            yield event.plain_result("页码/条数必须是整数")
            return

        try:
            client = ApiClient(email=self.Iwara_account, password=self.Iwara_password)
            client.login()

            # 若关键词为空 -> 不传入 user 参数；否则使用官方搜索字段
            params = {
                "sort": "views",
                "page": page_int,
                "limit": limit_int,
                "rating": "all",
            }
            if date:
                params['date'] = date

            r = client.get_videos(**params).json()
            results = r.get("results", [])
            total   = r.get("count", 0)

            if not results:
                yield event.plain_result("没有搜到匹配的视频。")
                return

            lines = [f"共 {total} 条，第 {page_int+1} 页："]
            for v in results:
                title   = v.get("title", "无标题")
                vid     = v.get("id")
                size    = self.pretty_size(v.get("file", {}).get("size", 0))
                views   = v.get("numViews", 0)
                likes   = v.get("numLikes", 0)
                lines.append(
                    f"【{title}】\n"
                    f"ID: {vid} | 大小: {size} | ▶{views:,} | 👍{likes:,}"
                )

            yield event.plain_result("\n\n".join(lines))

        except Exception as e:
            logger.error(f"[Iwarapage] {e}")
            yield event.plain_result(f"搜索失败：{e}")

    # -------------------------------------------------
    # 指令：iwara.thumb <video_id>
    # -------------------------------------------------
    @filter.command("iwarathumb")
    async def iwara_thumb(self, event: AstrMessageEvent, video_ID: str = None):
        """下载并发送指定视频的封面图"""
        if not video_ID:
            yield event.plain_result("请提供视频 ID，例如：iwarathumb abc123")
            return

        try:
            # 调用 ApiClient 下载封面
            client = ApiClient(email=self.Iwara_account, password=self.Iwara_password)
            client.login()
            thumb_path = client.download_video_thumbnail(path=self.Iwara_savepath, video_id=video_ID)

            # 发送图片
            from astrbot.api.message_components import Image
            yield event.chain_result([Image(file=thumb_path)])
            # 可选：发送完删除
            # os.remove(thumb_path)

        except Exception as e:
            logger.error(f"[Iwarathumb] {e}")
            yield event.plain_result(f"封面获取失败：{e}")

    # -------------------------------------------------
    # 指令：iwarahelp
    # -------------------------------------------------
    @filter.command("iwarahelp")
    async def iwara_help(self, event: AstrMessageEvent):
        """显示 Iwara 插件全部指令说明"""
        help_text = (
            "🎬 Iwara 插件指令说明\n"
            "————————————\n"
            "1. 下载视频\n"
            "   iwara <video_id>\n"
            "   例：iwara JxhNoTWKaoZzAV\n"
            "\n"
            "2. 热门视频\n"
            "   iwarapage [页码] [条数0-32] [年月]\n"
            "   例：iwarapage 0 5 2025-8\n"
            "\n"
            "3. 获取封面\n"
            "   iwarathumb <video_id>\n"
            "   例：iwarathumb JxhNoTWKaoZzAV\n"
            "\n"
        )
        yield event.plain_result(help_text)