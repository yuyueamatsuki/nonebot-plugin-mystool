from nonebot import on_command
from nonebot.adapters.onebot.v11 import PrivateMessageEvent
from nonebot.params import T_State, ArgPlainText
from .utils import *
from .data import UserAccount, UserData
from . import address as addr

get_address = on_command('address', aliases={'地址填写', '地址', '地址获取'}, priority=4, block=True)

get_address.__help__ = {
    "usage":     "get_address",
    "introduce": "获取地址ID"
}

@get_address.handle()
async def handle_first_receive(event: PrivateMessageEvent, state: T_State):
    await get_address.send("请跟随指引配合地址ID，请确保米游社内已经填写了至少一个地址，过程中随时输入退出即可退出")
    qq_account = event.user_id
    user_account = UserData.read_account_all(qq_account)
    if len(user_account) == 0:
        await get_address.finish("你没有配置cookie，请先配置cookie！")
    elif len(user_account) == 1:
        account = user_account[0]
    else:
        get_address.send('您有多个账号，您要配置一下哪个账号的地址ID？')
        ... # 发送账号
        ...
    get_address__(account, state)


@get_address.got('address_id',prompt='请输入你要选择的地址ID(Address_ID)')
async def _(event: PrivateMessageEvent, state: T_State, address_id: str = ArgPlainText('address_id')):
    if address_id == "退出":
        get_address.finish("已成功退出")
    if address_id in state['address_id']:
        state["address_id"] = address_id

        account = UserData.read_account(..., ...) # QQ、手机号
        account.addressID = address_id
        UserData.set_account(account, ..., ...) # QQ、手机号

        get_address.finish("地址写入完成")
    else:
        get_address.reject("您输入的地址id与上文的不匹配，请重新输入")

async def get_address__(account: UserAccount, state: T_State):
    state['address_id'] = []

    try:
        address_list: list[addr.Address] = addr.get(account)
    except:
        await get_address.finish("请求失败")
    if not address_list:
        await get_address.send("以下为查询结果：")
        for address in address_list:
            address_string = f"""\
            ----------
            省：{address.province}
            市：{address.city}
            区/县：{address.county}
            详细地址：{address.detail}
            联系电话：{address.phone}
            联系人：{address.name}
            地址ID(Address_ID)：{address.addressID}
            """
            state['address_id'].append(address.addressID)
            await get_address.send(address_string)
    else:
        await get_address.finish("您的该账号没有配置地址，请先前往米游社配置地址！")