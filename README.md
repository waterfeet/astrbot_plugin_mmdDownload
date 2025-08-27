# AstrBot 插件：Iwara MMD下载助手

> 浏览、下载并发送 Iwara 视频与封面！

---

## ✨ 功能一览

| 指令 | 功能说明 | 示例 |
|---|---|---|
| `iwarahelp` | 查看全部指令 | `iwarahelp` |
| `iwara <video_id>` | 下载视频并打包发送 | `iwara JxhNoTWKaoZzAV` |
| `iwarapage [页码] [条数0-32] [年月]` | 浏览列表，返回标题/ID/大小/播放量/点赞数） | `iwarasearch 0 32 2025-8` |
| `iwarathumb <video_id>` | 下载并发送封面原图 | `iwarathumb JxhNoTWKaoZzAV` |

- **断点续传**：网络中断后可自动续传，不重复下载已完成的字节。  
- **后台线程**：所有耗时操作均在线程池完成，不阻塞主事件循环。  

---
