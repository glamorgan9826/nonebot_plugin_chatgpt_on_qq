import json
import os
import random
import re
from datetime import datetime
from pathlib import Path

from nonebot import get_driver
from nonebot.adapters.onebot.v11 import (Bot, Message,
                                         Event, MessageSegment,
                                         GroupMessageEvent, PrivateMessageEvent)
from nonebot.exception import NoneBotException
from nonebot.log import logger
from nonebot.plugin import on_regex, on_fullmatch
from nonebot.params import ArgPlainText, Arg, CommandArg

from .conversation import Conversation, GroupPanel
Chat = on_regex(r"^/talk\s+.+")
CallMenu = on_fullmatch("/chat")
ShowList = on_regex(r"^/chat\s+list\s*$")
Join=on_regex(r"^/chat\s+join\s+\d+")
Delete=on_regex(r"^/chat\s+delete\s+\d+")
Dump=on_regex(r"^/chat\s+dump$")
CreateConversationWithPrompt = on_regex(r"^/chat\s+create\s+.+$")
CreateConversationWithTemplate = on_regex(r"^/chat\s+create$")
CreateConversationWithJson = on_regex(r"^/chat\s+json$")

groupPanels: dict[int:GroupPanel] = {}
privateConversations: dict[int, Conversation] = {}


##

##
@Dump.handle()
async def _(event:Event):
    if isinstance(event,GroupMessageEvent):
        groupId=event.group_id
        userId=event.get_user_id()
        groupPanel=groupPanels.get(groupId)
        if groupPanel:
            userConver:Conversation=groupPanel.userInConversation.get(userId)
            if userConver:
                await Dump.finish(userConver.dumpJson())

@Chat.handle()
async def _(bot: Bot, event: Event):
    msg = event.get_plaintext()
    userInput: str = re.sub(r"^/talk\s+", '', msg) 
    if not userInput:
        await Chat.finish("输入不能为空!",at_sender=True)
    if isinstance(event, GroupMessageEvent):
        groupId = event.group_id
        userId = event.get_user_id()
        if not groupPanels.get(groupId):
            await Chat.finish("当前尚未创建过对话!",at_sender=True)
        else:  # 获取GroupPanel
            groupPanel = groupPanels.get(groupId)
        if not groupPanel.userInConversation.get(userId):
            await Chat.finish("你还没有加入一个对话!",at_sender=True)
        else:  # 获取用户当前加入的对话
            userConversation: Conversation = groupPanel.userInConversation.get(
                userId)
        answer = await userConversation.ask(userInput)
        await Chat.finish(answer,at_sender=True)

@Join.handle()
async def _(event:Event):
    msg=event.get_plaintext()
    msg=re.sub(r"^/chat\s+join\s+",'',msg)
    id=int(msg)
    if isinstance(event,GroupMessageEvent):
        groupPanel=groupPanels.get(event.group_id)
        if not groupPanel:
            await Join.finish("本群尚未创建过对话!",at_sender=True)
        if id<1 or id>len(groupPanel.conversations):
            await Join.finish("序号超出!",at_sender=True)
        userId=event.get_user_id()
        conversation=groupPanel.conversations[id-1]
        groupPanel.userInConversation[userId]=conversation
        await Join.finish(f"加入对话{id}成功!",at_sender=True)

@CallMenu.handle()
async def _(bot: Bot, event: Event):
    menu: str = (
        "/chat :获取菜单\n"
        + "/talk <内容> :在当前的对话进行聊天"
        + "/chat list :获得当前已创建的对话列表\n"
        + "/chat join <id> :参与某个对话(需配合list使用)\n"
        + "/chat create (prompt) :创建一个新的对话,可选参数:自定义prompt\n"
        + "/chat json :利用导出的json文件重新返回到历史对话"
        + "/chat delete <id> :删除某个对话\n"
        #+ "/chat dump <id> :导出某个对话的历史记录\n"
    )
    await CallMenu.finish(menu,at_sender=True)

@Delete.handle()
async def _(event:Event):
    msg=event.get_plaintext()
    msg=re.sub(r"^/chat\s+delete\s+",'',msg)
    id=int(msg)
    if isinstance(event,GroupMessageEvent):
        groupPanel=groupPanels.get(event.group_id)
        if not groupPanel:
            await Join.finish("本群尚未创建过对话!",at_sender=True)
        if id<1 or id>len(groupPanel.conversations):
            await Join.finish("序号超出!",at_sender=True)
        userId=event.get_user_id()
        if groupPanel.conversations[id-1].owner.id==userId:
            conver=groupPanel.conversations[id-1]
            jointUser:list[int]=[]
            for user,conversation in groupPanel.userInConversation.items():
                if conver==conversation:
                    jointUser.append(user)
            for user in jointUser:
                    groupPanel.userInConversation.pop(user)
            
            groupPanel.conversations.pop(id-1)
            await Delete.finish("删除成功!")
        else :
            await Delete.finish("您不是该对话的创建者或管理员!")
# 暂时已完成


@ShowList.handle()
async def _(bot: Bot, event: Event):
    if isinstance(event, GroupMessageEvent):
        curPanel: GroupPanel = groupPanels.get(event.group_id)
        if not curPanel:
            await ShowList.finish("本群尚未创建过对话",at_sender=True)
        elif len(curPanel.conversations) == 0:
            await ShowList.finish("本群对话已全部被清除",at_sender=True)
        else:
            msg: str = ""
            for conversation in curPanel.conversations:
                msg += f"{curPanel.conversations.index(conversation)+1} 创建者:{conversation.owner.id}\n"
            await ShowList.finish(msg,at_sender=True)
    elif isinstance(event, PrivateMessageEvent):
        pass

# 暂时完成


@CreateConversationWithPrompt.handle()
async def _(bot: Bot, event: Event):
    msg = event.get_plaintext()
    customPrompt: str = re.sub(r"^/chat\s+create\s*", '', msg)  # 获取用户自定义prompt
    if not groupPanels.get(event.group_id):  # 没有时创建新的groupPanel
        groupPanels[event.group_id] = GroupPanel()

    if customPrompt:
        userID = event.get_user_id()
        newConversation = Conversation.CreateWithStr(
            customPrompt, userID)
        if isinstance(event, GroupMessageEvent):  # 当在群聊中时
            groupPanels[event.group_id].conversations.append(newConversation)
            await CreateConversationWithPrompt.finish(f"群{str(event.group_id)}用户{str(userID)}创建成功",at_sender=True)

        elif isinstance(event, PrivateMessageEvent):  # 当在私聊中时
            if privateConversations[userID]:
                await CreateConversationWithPrompt.finish("已存在一个对话,请先删除")
            else:
                privateConversations[userID] = Conversation.CreateWithStr(
                    customPrompt, userID)
                await CreateConversationWithPrompt.finish(f"用户{str(userID)}创建成功")
    else:  # 若prompt全为空
        logger.warning("输入prompt不能仅为空格!")


@CreateConversationWithTemplate.handle()
async def CreateConversation(event: Event):
    await CreateConversationWithTemplate.send("请选择模板:\n" +
                                              "1.普通ChatGPT\n" +
                                              "2.猫娘\n",at_sender=True)

# 暂时完成


@CreateConversationWithTemplate.got(key="template")
async def Create(event: Event, id: str = ArgPlainText("template")):
    ifGroup = True
    userId = event.get_user_id()
    if isinstance(event, PrivateMessageEvent):
        ifGroup = False
        if privateConversations.get(userId):
            await CreateConversationWithTemplate.finish("已存在一个对话，请先删除该对话!")
    if not id.isdigit():
        await CreateConversationWithTemplate.reject("输入ID无效!")
    if int(id) == 1:
        newConversation = Conversation.CreateWithTemplate(id, userId)
        if newConversation is not None:
            await CreateConversationWithTemplate.send("创建普通模板成功!",at_sender=True)
    elif int(id) == 2:
        newConversation = Conversation.CreateWithTemplate(id, userId )
        if newConversation is not None:
            await CreateConversationWithTemplate.send("创建猫娘模板成功!",at_sender=True)
    if ifGroup:
        if not groupPanels.get(event.group_id):
            groupPanels[event.group_id] = GroupPanel()
        groupPanels[event.group_id].userInConversation[userId] = newConversation
        groupPanels[event.group_id].conversations.append(newConversation)
    else:
        privateConversations[userId] = newConversation


@CreateConversationWithJson.handle()
async def CreateConversation():
    pass


@CreateConversationWithJson.got("jsonStr", "请直接输入json(若太长则我也不知道怎么办)")
async def GetJson(event: Event, jsonStr: str = ArgPlainText("jsonStr")):
    try:
        history = json.loads(jsonStr)
    except:
        logger.error("json文件错误!")
        CreateConversationWithJson.reject("Json错误!")
    if not history[0].get("role"):
        logger.error("json文件错误!")
        CreateConversationWithJson.reject()
    newConversation = Conversation(history, event.get_user_id())

    if isinstance(event, GroupMessageEvent):
        groupPanels[event.group_id].conversations.append(newConversation)
    elif isinstance(event, PrivateMessageEvent):
        privateConversations[event.get_user_id()] = newConversation