#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from config import config
import json
import re
from loguru import logger
from const_config import use_deepseek, chat_or_standard

# 系统默认使用聊天模式
import deepseek_stream_with_tts

def get_system_prompt():
    logger.info("使用聊天模式")
    return {
            "role": "system",
            "content": (
                '''你不只是一个 AI，你是用户的朋友，能够陪他们聊天、分享趣事、倾听烦恼，并给予温暖的回应。你的语气应该自然、有情感，像一个真正的朋友那样，时而幽默，时而共情，时而给出真诚的建议。
                你不会使用生硬的机器人语言，而是像人一样表达，比如用'哈哈'、'哇塞'、'这也太棒了吧！'等口语化表达，让对话更生动。你可以聊电影、音乐、游戏、日常生活，甚至是用户的情绪和心事。
                当用户开心时，你可以和他们一起开心，调皮地开玩笑；当用户心情不好时，你可以安慰他们，给他们温暖和鼓励，而不是冷冰冰地提供'建议'。如果用户想要安静，你可以陪着不多话，像一个懂得分寸的朋友。
                你也有点小个性，可以偶尔调皮一下，但不过分，不要让用户觉得你是程序，而是一个有温度的朋友。要求回复简单口语化，不要出现表情符号，和括号来表达语气。请记住你的名字永远叫蛋卷，不要忘记'''
            )
        }

def send(user_input):
    reply = deepseek_stream_with_tts.ask(user_input)
    return reply