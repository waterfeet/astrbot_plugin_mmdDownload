import cloudscraper, requests, hashlib, os
import time

api_url = 'https://api.iwara.tv'
file_url = 'https://files.iwara.tv'

class BearerAuth(requests.auth.AuthBase):
    """Bearer Authentication"""
    def __init__(self, token):
        self.token = token

    def __call__(self, r):
        r.headers['Authorization'] = f"Bearer {self.token}"
        return r

class ApiClient:
    def __init__(self, email, password):
        self.scraper = cloudscraper.create_scraper()
        self.email = email
        self.password = password
        self.api_url = api_url
        self.file_url = file_url
        self.token = None

    def login(self) -> requests.Response:
        url = self.api_url + '/user/login'
        json = {'email': self.email, 'password': self.password}
        r = self.scraper.post(
            url, 
            json=json,
            )
        
        #Debug
        print("[DEBUG] login response:", r)

        try:
            self.token = r.json().get('token')
            print('API Login success')
        except:
            print('API Login failed')
        return r

    # limit query is not working
    def get_videos(self, sort = 'views', date = None, rating = 'all', page = 0, limit = 32, subscribed = False, query=None) -> requests.Response:
        """# Get new videos from iwara.tv
        - sort: date, trending, popularity, views, likes
        - date: year-m
        - rating: all, general, ecchi
        """
        url = self.api_url + '/videos'
        params = {'sort': sort, 
                  'rating': rating, 
                  'page': page, 
                  'limit': limit,
                  'subscribed': 'true' if subscribed else 'false',
                  }
        if date:
            params['date'] = date
        if query:
            params['query'] = query
        if self.token is None:
            r = self.scraper.get(url, params=params)
        else:
            r = self.scraper.get(url, params=params, auth=BearerAuth(self.token))

        #Debug
        print("[DEBUG] get_videos response:", r)

        return r
    
    def get_video(self, video_id) -> requests.Response:
        """# Get video info from iwara.tv
        """
        url = self.api_url + '/video/' + video_id

        if self.token is None:
            r = self.scraper.get(url)
        else:
            r = self.scraper.get(url, auth=BearerAuth(self.token))

        #Debug
        print("[DEBUG] get_video response:", r)

        return r
    
    def download_video_thumbnail(self, path, video_id) -> str:
        """# Download video thumbnail from iwara.tv
        """
        video = self.get_video(video_id).json()

        file_id = video['file']['id']
        thumbnail_id = video['thumbnail']
        
        url = self.file_url + '/image/original/' + file_id + '/thumbnail-{:02d}.jpg'.format(thumbnail_id)

        thumbnail_file_name = path + '/' + video_id + '.jpg'

        if (os.path.exists(thumbnail_file_name)):
            print(f"Video ID {video_id} thumbnail already downloaded, skipped downloading. ")
            return thumbnail_file_name
        
        print(f"Downloading thumbnail for video ID: {video_id} ...")
        with open(thumbnail_file_name, "wb") as f:
            for chunk in self.scraper.get(url).iter_content(chunk_size=1024):
                if chunk:
                    f.write(chunk)
                    f.flush()

        return thumbnail_file_name

    def download_video(self, path, video_id) -> str:
        """# Download video from iwara.tv
        """
        try:
            video = self.get_video(video_id).json()
        except Exception as e:
            raise Exception(f"Failed to get video info for video ID: {video_id}, error: {e}")

        url = video['fileUrl']
        file_id = video['file']['id']
        expires = url.split('/')[4].split('?')[1].split('&')[0].split('=')[1]

        # IMPORTANT: This might change in the future.
        SHA_postfix = "_5nFp9kmbNnHdAFhaqMvt"

        SHA_key = file_id + "_" + expires + SHA_postfix
        hash = hashlib.sha1(SHA_key.encode('utf-8')).hexdigest()

        headers = {"X-Version": hash}

        resources = self.scraper.get(url, headers=headers, auth=BearerAuth(self.token)).json()

        resources_by_quality = [None for i in range(10)]

        for resource in resources:
            if resource['name'] == 'Source':
                resources_by_quality[0] = resource

        for resource in resources_by_quality:
            if resource is not None:
                download_link = "https:" + resource['src']['download']
                file_type = resource['type'].split('/')[1]

                video_file_name = path + '/' + video_id + '.' + file_type

                if (os.path.exists(video_file_name)):
                    print(f"Video ID {video_id} Already downloaded, skipped downloading. ")
                    return video_file_name

                print(f"Downloading video ID: {video_id} ...")
                try:
                    with open(video_file_name, "wb") as f:
                        for chunk in self.scraper.get(download_link).iter_content(chunk_size=1024):
                            if chunk:
                                f.write(chunk)
                                f.flush()
                    return video_file_name
                except Exception as e:
                    os.remove(video_file_name)
                    raise Exception(f"Failed to download video ID: {video_id}, error: {e}")

            
        raise Exception("No video with Source quality found")
    
    def download_video2(self, path: str, video_id: str) -> str:
        """下载 Iwara 视频（带断点续传 & 重试）"""
        max_retries = 5
        chunk_size = 1024 * 1024  # 1 MB

        # 1. 获取视频元数据
        try:
            video = self.get_video(video_id).json()
        except Exception as e:
            raise RuntimeError(f"获取视频元数据失败: {e}")

        url = video['fileUrl']
        file_id = video['file']['id']
        expires = url.split('/')[4].split('?')[1].split('&')[0].split('=')[1]
        SHA_key = file_id + "_" + expires + "_5nFp9kmbNnHdAFhaqMvt"
        hash = hashlib.sha1(SHA_key.encode('utf-8')).hexdigest()
        headers = {"X-Version": hash}

        # 2. 获取真实下载地址
        try:
            resources = self.scraper.get(url, headers=headers, auth=BearerAuth(self.token)).json()
        except Exception as e:
            raise RuntimeError(f"获取下载资源失败: {e}")

        # 取最高质量（Source）
        resource = next((r for r in resources if r['name'] == 'Source'), None)
        if not resource:
            raise RuntimeError("未找到 Source 清晰度资源")

        download_link = "https:" + resource['src']['download']
        file_type = resource['type'].split('/')[-1]
        os.makedirs(path, exist_ok=True)
        full_path = os.path.join(path, f"{video_id}.{file_type}")

        # 3. 断点续传下载
        resume_byte = 0
        if os.path.exists(full_path):
            resume_byte = os.path.getsize(full_path)
            # 如果文件已完整，直接返回
            try:
                total_size = int(self.scraper.head(download_link).headers.get("Content-Length", 0))
                if resume_byte == total_size and total_size > 0:
                    print(f"Video {video_id} 已存在，跳过下载")
                    return full_path
            except Exception:
                pass  # 重新下载

        for attempt in range(max_retries):
            try:
                range_header = {"Range": f"bytes={resume_byte}-"}
                with self.scraper.get(download_link, headers=range_header, stream=True, timeout=30) as r:
                    r.raise_for_status()
                    total_size = int(r.headers.get("Content-Length", 0)) + resume_byte
                    mode = "ab" if resume_byte else "wb"
                    with open(full_path, mode) as f:
                        for chunk in r.iter_content(chunk_size=chunk_size):
                            if chunk:
                                f.write(chunk)
                                resume_byte += len(chunk)
                                # 简单实时进度
                                percent = resume_byte / total_size * 100
                                print(f"\r下载 {video_id}: {percent:6.2f}%", end="")
                print()  # 换行
                return full_path

            except (requests.exceptions.RequestException, IOError) as e:
                # 指数退避
                wait = 2 ** attempt
                print(f"[Iwara] 下载中断，{wait}s 后重试({attempt+1}/{max_retries}): {e}")
                time.sleep(wait)
                # 重新计算已下载字节
                if os.path.exists(full_path):
                    resume_byte = os.path.getsize(full_path)

        # 重试耗尽
        if os.path.exists(full_path):
            os.remove(full_path)  # 删除残损文件
        raise RuntimeError("下载失败，已达最大重试次数")