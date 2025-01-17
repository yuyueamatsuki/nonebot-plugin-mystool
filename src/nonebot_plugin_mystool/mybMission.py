"""
### 米游币任务相关
"""
import asyncio
import traceback
from typing import Any, Dict, List, Literal, NewType, Tuple, Union

import httpx
import tenacity

from .config import mysTool_config as conf
from .data import UserAccount
from .utils import check_login, custom_attempt_times, generateDS, logger
from .bbsAPI import device_login, device_save

URL_SIGN = "https://bbs-api.mihoyo.com/apihub/app/api/signIn"
URL_GET_POST = "https://bbs-api.mihoyo.com/post/api/getForumPostList?forum_id={}&is_good=false&is_hot=false&page_size=20&sort_type=1"
URL_READ = "https://bbs-api.mihoyo.com/post/api/getPostFull?post_id={}"
URL_LIKE = "https://bbs-api.mihoyo.com/apihub/sapi/upvotePost"
URL_SHARE = "https://bbs-api.mihoyo.com/apihub/api/getShareConf?entity_id={}&entity_type=1"
URL_MISSION = "https://api-takumi.mihoyo.com/apihub/wapi/getMissions?point_sn=myb"
URL_MISSION_STATE = "https://api-takumi.mihoyo.com/apihub/wapi/getUserMissionsState?point_sn=myb"
HEADERS = {
    "Host": "bbs-api.mihoyo.com",
    "Referer": "https://app.mihoyo.com",
    'User-Agent': conf.device.USER_AGENT_ANDROID_OTHER,
    "x-rpc-app_version": conf.device.X_RPC_APP_VERSION,
    "x-rpc-channel": conf.device.X_RPC_CHANNEL_ANDROID,
    "x-rpc-client_type": "2",
    "x-rpc-device_id": None,
    "x-rpc-device_model": conf.device.X_RPC_DEVICE_MODEL_ANDROID,
    "x-rpc-device_name": conf.device.X_RPC_DEVICE_NAME_ANDROID,
    "x-rpc-sys_version": conf.device.X_RPC_SYS_VERSION_ANDROID,
    "Accept-Encoding": "gzip",
    "Connection": "Keep-Alive",
    "DS": None
}
HEADERS_MISSION = {
    "Host": "api-takumi.mihoyo.com",
    "Origin": "https://webstatic.mihoyo.com",
    "Connection": "keep-alive",
    "Accept": "application/json, text/plain, */*",
    "User-Agent": conf.device.USER_AGENT_MOBILE,
    "Accept-Language": "zh-CN,zh-Hans;q=0.9",
    "Referer": "https://webstatic.mihoyo.com/",
    "Accept-Encoding": "gzip, deflate, br"
}
GAME_ID = {
    "bh3": {
        "gids": 1,
        "fid": 1
    },
    "ys": {
        "gids": 2,
        "fid": 26
    },
    "bh2": {
        "gids": 3,
        "fid": 30
    },
    "wd": {
        "gids": 4,
        "fid": 37
    },
    "xq": {
        "gids": 5,
        "fid": 52
    }
}

Prograss_Now = NewType("Prograss_Now", int)
Myb_Num = NewType("Myb_Num", int)


class Mission:
    """
    任务信息数据

    通过对象的`keyName`属性来判断该任务是什么\n
    各个任务对应的`keyName`值在类属性中\n
    (`Mission.SIGN`, `Mission.VIEW`, `Mission.LIKE`, `Mission.SHARE`)
    """
    SIGN = "continuous_sign"
    '''签到任务的 keyName'''
    VIEW = "view_post_0"
    '''阅读任务的 keyName'''
    LIKE = "post_up_0"
    '''点赞任务的 keyName'''
    SHARE = "share_post_0"
    '''分享任务的 keyName'''

    def __init__(self, mission_dict: dict) -> None:
        self.mission_dict = mission_dict
        try:
            for func in dir(Mission):
                if func.startswith("__"):
                    continue
                getattr(self, func)
        except KeyError:
            logger.error(conf.LOG_HEAD + "米游币任务数据 - 初始化对象: dict数据不正确")
            logger.debug(conf.LOG_HEAD + traceback.format_exc())

    @property
    def points(self) -> int:
        """
        任务米游币奖励
        """
        return self.mission_dict["points"]

    @property
    def name(self) -> str:
        """
        任务名字，如 讨论区签到
        """
        return self.mission_dict["name"]

    @property
    def keyName(self):
        """
        任务代号，如 continuous_sign
        """
        for name in (self.SIGN, self.VIEW, self.LIKE, self.SHARE):
            if name == self.mission_dict["mission_key"]:
                return name

    @property
    def totalTimes(self) -> int:
        """
        任务完成的次数要求
        """
        return self.mission_dict["threshold"]


class Action:
    """
    米游币任务相关(需先初始化对象)

    类属性有`NAME_TO_FUNC`，是任务`keyName`与函数的对应关系
    """
    Action_Method = NewType("Action_Method", Any)

    def __init__(self, account: UserAccount) -> None:
        self.account = account
        self.headers = HEADERS.copy()
        self.headers["x-rpc-device_id"] = account.deviceID_2
        self.client = httpx.AsyncClient(cookies=account.cookie)

    async def async_init(self):
        """
        初始化米游币任务(异步，返回`self`对象)(执行deviceLogin和saveDevice)
        """
        await device_login(self.account)
        await device_save(self.account)
        return self

    async def sign(self, game: Literal["bh3", "ys", "bh2", "wd", "xq"]) -> Union[int, Literal[-1, -2, -3]]:
        """
        签到

        参数:
            `game`: 游戏简称

        - 若返回 `-1` 说明用户登录失效
        - 若返回 `-2` 说明服务器没有正确返回
        - 若返回 `-3` 说明请求失败
        """
        data = {"gids": GAME_ID[game]["gids"]}
        self.headers["DS"] = generateDS(data)
        res = await self.client.post(URL_SIGN, headers=self.headers, json=data, timeout=conf.TIME_OUT)
        if not check_login(res.text):
            logger.info(
                conf.LOG_HEAD + "米游币任务 - 讨论区签到: 用户 {} 登录失效".format(self.account.phone))
            logger.debug(conf.LOG_HEAD + "网络请求返回: {}".format(res.text))
            return -1
        try:
            return res.json()["data"]["points"]
        except KeyError:
            logger.error(conf.LOG_HEAD + "米游币任务 - 讨论区签到: 服务器没有正确返回")
            logger.debug(conf.LOG_HEAD + "网络请求返回: {}".format(res.text))
            logger.debug(conf.LOG_HEAD + traceback.format_exc())
            return -2
        except:
            logger.error(conf.LOG_HEAD + "米游币任务 - 讨论区签到: 请求失败")
            logger.debug(conf.LOG_HEAD + traceback.format_exc())
            return -3

    async def get_posts(self, game: Literal["bh3", "ys", "bh2", "wd", "xq"], retry: bool = True) -> Union[List[str], None]:
        """
        获取文章ID列表，若失败返回`None`

        参数:
            `game`: 游戏简称
            `retry`: 是否允许重试
        """
        postID_list = []
        try:
            self.headers["DS"] = generateDS(platform="android")
            async for attempt in tenacity.AsyncRetrying(stop=custom_attempt_times(retry), reraise=True, wait=tenacity.wait_fixed(conf.SLEEP_TIME_RETRY)):
                with attempt:
                    res = await self.client.get(URL_GET_POST.format(GAME_ID[game]["fid"]), headers=self.headers, timeout=conf.TIME_OUT)
                    data = res.json()["data"]["list"]
                    for post in data:
                        if post["self_operation"]["attitude"] == 0:
                            postID_list.append(post['post']['post_id'])
                    break
        except KeyError:
            logger.error(conf.LOG_HEAD + "米游币任务 - 获取文章列表: 服务器没有正确返回")
            logger.debug(conf.LOG_HEAD + "网络请求返回: {}".format(res.text))
            logger.debug(conf.LOG_HEAD + traceback.format_exc())
            return None
        except:
            logger.error(conf.LOG_HEAD + "米游币任务 - 获取文章列表: 网络请求失败")
            logger.debug(conf.LOG_HEAD + traceback.format_exc())
            return None
        return postID_list

    async def read(self, game: Literal["bh3", "ys", "bh2", "wd", "xq"], readTimes: int = 5, retry: bool = True):
        """
        阅读

        参数:
            `game`: 游戏简称
            `readTimes`: 阅读文章数
            `retry`: 是否允许重试

        - 若执行成功，返回 `1`
        - 若返回 `-1` 说明用户登录失效
        - 若返回 `-2` 说明服务器没有正确返回或请求失败
        - 若返回 `-3` 说明请求失败
        - 若返回 `-4` 说明获取文章失败
        """
        count = 0
        postID_list = await self.get_posts(game)
        if postID_list is None:
            return -4
        while count < readTimes:
            for postID in postID_list:
                if count == readTimes:
                    break
                self.headers["DS"] = generateDS(platform="android")
                try:
                    async for attempt in tenacity.AsyncRetrying(stop=custom_attempt_times(retry), reraise=True, wait=tenacity.wait_fixed(conf.SLEEP_TIME_RETRY)):
                        with attempt:
                            res = await self.client.get(URL_READ.format(postID), headers=self.headers, timeout=conf.TIME_OUT)
                            if not check_login(res.text):
                                logger.info(
                                    conf.LOG_HEAD + "米游币任务 - 阅读: 用户 {} 登录失效".format(self.account.phone))
                                logger.debug(conf.LOG_HEAD +
                                             "网络请求返回: {}".format(res.text))
                                return -1
                            if res.json()["message"] == "帖子不存在":
                                continue
                            if "self_operation" not in res.json()["data"]["post"]:
                                raise ValueError
                            count += 1
                except KeyError and ValueError:
                    logger.error(conf.LOG_HEAD + "米游币任务 - 阅读: 服务器没有正确返回")
                    logger.debug(conf.LOG_HEAD +
                                 "网络请求返回: {}".format(res.text))
                    logger.debug(conf.LOG_HEAD + traceback.format_exc())
                    return -2
                except:
                    logger.error(conf.LOG_HEAD + "米游币任务 - 阅读: 网络请求失败")
                    logger.debug(conf.LOG_HEAD + traceback.format_exc())
                    return -3
                await asyncio.sleep(conf.SLEEP_TIME)
            postID_list = await self.get_posts(game)
            if postID_list is None:
                return -4

        return 1

    async def like(self, game: Literal["bh3", "ys", "bh2", "wd", "xq"], likeTimes: int = 10, retry: bool = True):
        """
        点赞文章

        参数:
            `game`: 游戏简称
            `likeTimes`: 点赞次数
            `retry`: 是否允许重试

        - 若执行成功，返回 `1`
        - 若返回 `-1` 说明用户登录失效
        - 若返回 `-2` 说明服务器没有正确返回或请求失败
        - 若返回 `-3` 说明请求失败
        - 若返回 `-4` 说明获取文章失败
        """
        count = 0
        postID_list = await self.get_posts(game)
        if postID_list is None:
            return -4
        while count < likeTimes:
            for postID in postID_list:
                if count == likeTimes:
                    break
                self.headers["DS"] = generateDS(platform="android")
                try:
                    async for attempt in tenacity.AsyncRetrying(stop=custom_attempt_times(retry), reraise=True, wait=tenacity.wait_fixed(conf.SLEEP_TIME_RETRY)):
                        with attempt:
                            res = await self.client.post(URL_LIKE, headers=self.headers, json={'is_cancel': False, 'post_id': postID}, timeout=conf.TIME_OUT)
                            if not check_login(res.text):
                                logger.info(
                                    conf.LOG_HEAD + "米游币任务 - 点赞: 用户 {} 登录失效".format(self.account.phone))
                                logger.debug(conf.LOG_HEAD +
                                             "网络请求返回: {}".format(res.text))
                                return -1
                            if res.json()["message"] == "帖子不存在":
                                continue
                            elif res.json()["message"] != "OK":
                                raise ValueError
                            count += 1
                except KeyError and ValueError:
                    logger.error(conf.LOG_HEAD + "米游币任务 - 点赞: 服务器没有正确返回")
                    logger.debug(conf.LOG_HEAD +
                                 "网络请求返回: {}".format(res.text))
                    logger.debug(conf.LOG_HEAD + traceback.format_exc())
                    return -2
                except:
                    logger.error(conf.LOG_HEAD + "米游币任务 - 点赞: 网络请求失败")
                    logger.debug(conf.LOG_HEAD + traceback.format_exc())
                    return -3
                await asyncio.sleep(conf.SLEEP_TIME)
            postID_list = await self.get_posts(game)
            if postID_list is None:
                return -4

        return 1

    async def share(self, game: Literal["bh3", "ys", "bh2", "wd", "xq"], retry: bool = True):
        """
        分享文章

        参数:
            `game`: 游戏简称
            `retry`: 是否允许重试

        - 若执行成功，返回 `1`
        - 若返回 `-1` 说明用户登录失效
        - 若返回 `-2` 说明服务器没有正确返回
        - 若返回 `-3` 说明请求失败
        - 若返回 `-4` 说明网络请求发送成功，但是可能未签到成功
        - 若返回 `-5` 说明获取文章失败
        """
        postID_list = await self.get_posts(game)
        if postID_list is None:
            return -5
        try:
            async for attempt in tenacity.AsyncRetrying(stop=custom_attempt_times(retry), reraise=True, wait=tenacity.wait_fixed(conf.SLEEP_TIME_RETRY)):
                with attempt:
                    self.headers["DS"] = generateDS(platform="android")
                    res = await self.client.get(URL_SHARE.format(postID_list[0]), headers=self.headers, timeout=conf.TIME_OUT)
                    if not check_login(res.text):
                        logger.info(
                            conf.LOG_HEAD + "米游币任务 - 分享: 用户 {} 登录失效".format(self.account.phone))
                        logger.debug(conf.LOG_HEAD +
                                     "网络请求返回: {}".format(res.text))
                        return -1
                    if res.json()["message"] == "帖子不存在":
                        continue
                    elif res.json()["message"] != "OK":
                        return -4
        except KeyError and ValueError:
            logger.error(conf.LOG_HEAD + "米游币任务 - 分享: 服务器没有正确返回")
            logger.debug(conf.LOG_HEAD + "网络请求返回: {}".format(res.text))
            logger.debug(conf.LOG_HEAD + traceback.format_exc())
            return -2
        except:
            logger.error(conf.LOG_HEAD + "米游币任务 - 分享: 网络请求失败")
            logger.debug(conf.LOG_HEAD + traceback.format_exc())
            return -3
        return 1

    NAME_TO_FUNC: Dict[str, Action_Method] = {
        Mission.SIGN: sign,
        Mission.VIEW: read,
        Mission.LIKE: like,
        Mission.SHARE: share
    }


async def get_missions(account: UserAccount):
    """
    获取米游币任务信息

    - 若返回 `-1` 说明用户登录失效
    - 若返回 `-2` 说明服务器没有正确返回
    - 若返回 `-3` 说明请求失败
    """
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(URL_MISSION, headers=HEADERS_MISSION, cookies=account.cookie, timeout=conf.TIME_OUT)
        if not check_login(res.text):
            logger.info(conf.LOG_HEAD +
                        "获取米游币任务列表 - 用户 {} 登录失效".format(account.phone))
            logger.debug(conf.LOG_HEAD + "网络请求返回: {}".format(res.text))
            return -1
        mission_list: List[Mission] = []
        for mission in res.json()["data"]["missions"]:
            mission_list.append(Mission(mission))
        return mission_list
    except KeyError:
        logger.error(conf.LOG_HEAD + "获取米游币任务列表 - 服务器没有正确返回")
        logger.debug(conf.LOG_HEAD + "网络请求返回: {}".format(res.text))
        logger.debug(conf.LOG_HEAD + traceback.format_exc())
        return -2
    except:
        logger.error(conf.LOG_HEAD + "获取米游币任务列表 - 请求失败")
        logger.debug(conf.LOG_HEAD + traceback.format_exc())
        return -3


async def get_missions_state(account: UserAccount) -> Tuple[List[Tuple[Mission, Prograss_Now]], Myb_Num]:
    """
    获取米游币任务完成情况\n
    返回数据格式:
    >>> tuple[ list[ tuple[任务信息对象, 当前进度] ], 用户当前米游币数量 ]

    - 若返回 `-1` 说明用户登录失效
    - 若返回 `-2` 说明服务器没有正确返回
    - 若返回 `-3` 说明请求失败
    """
    missions: List[Mission] = await get_missions(account)
    if isinstance(missions, int):
        if missions == -1:
            return -1
        elif missions == -2:
            return -2
        elif missions == -3:
            return -3
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(URL_MISSION_STATE, headers=HEADERS_MISSION, cookies=account.cookie, timeout=conf.TIME_OUT)
        if not check_login(res.text):
            logger.info(conf.LOG_HEAD +
                        "获取米游币任务完成情况 - 用户 {} 登录失效".format(account.phone))
            logger.debug(conf.LOG_HEAD + "网络请求返回: {}".format(res.text))
            return -1
        state_list: List[Tuple[Mission, Prograss_Now]] = []
        data = res.json()["data"]
        for mission in missions:
            try:
                state_list.append((mission, list(filter(lambda state: state["mission_key"] ==
                                                        mission.keyName, data["states"]))[0]["happened_times"]))
            except IndexError:
                state_list.append((mission, 0))
        return (state_list, data["total_points"])
    except KeyError:
        logger.error(conf.LOG_HEAD + "获取米游币任务完成情况 - 服务器没有正确返回")
        logger.debug(conf.LOG_HEAD + "网络请求返回: {}".format(res.text))
        logger.debug(conf.LOG_HEAD + traceback.format_exc())
        return -2
    except:
        logger.error(conf.LOG_HEAD + "获取米游币任务完成情况 - 请求失败")
        logger.debug(conf.LOG_HEAD + traceback.format_exc())
        return -3
