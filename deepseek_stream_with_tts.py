#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
DeepSeek流式对话模块
实现与DeepSeek AI的流式对话和实时语音合成
"""

import os
import json
import pickle
import requests
import threading
from queue import Queue
from loguru import logger
from tts_stream import TTSManager
from const_config import sfapikey

# API配置
DEEPSEEK_API_URL = "https://api.siliconflow.cn/v1/chat/completions"
DEEPSEEK_API_KEY = sfapikey
CONTEXT_FILE = "message.data"
MAX_TOKENS_THRESHOLD = 1200
RESPONSE_END_MARKER = "[END]"


class DeepSeekChat:
    """DeepSeek流式对话类，处理对话流程和TTS集成"""
    
    def __init__(self):
        """初始化DeepSeek对话管理器"""
        # 对话状态
        self.messages = []
        
        # TTS集成
        self.response_queue = Queue()
        self.tts_manager = TTSManager(self.response_queue)
        
        # 启动TTS线程
        self._start_tts_thread()
        
        # API设置
        self.headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
    
    def _start_tts_thread(self):
        """启动TTS处理线程"""
        tts_thread = threading.Thread(
            target=self.tts_manager.start_tts, 
            daemon=True
        )
        tts_thread.start()
        logger.debug("TTS线程已启动")
    
    def initialize_system(self):
        """初始化系统提示和对话上下文"""
        self.messages = []
        
        # 延迟导入，避免循环导入问题
        # 仅在此函数中导入get_system_prompt
        from prompt_and_deal import get_system_prompt
        system_message = get_system_prompt()
        self.messages.append(system_message)
        logger.info("系统提示已初始化")
    
    def _prepare_api_payload(self):
        """准备API请求参数"""
        return {
            "model": "deepseek-ai/DeepSeek-V3",
            "messages": self.messages,
            "stream": True,  # 启用流式返回
            "max_tokens": 1024,
            "stop": ["null"],
            "temperature": 0.7,
            "top_p": 0.7,
            "top_k": 50,
            "frequency_penalty": 0.5,
            "n": 1,
            "response_format": {"type": "text"}
        }
    
    def _stream_api_response(self):
        """
        以流式方式获取API响应
        
        返回:
            元组 (ai_response, total_tokens)
        """
        payload = self._prepare_api_payload()
        ai_response = ""
        reasoning_response = ""
        total_tokens = 0
        
        try:
            # 发送API请求
            response = requests.post(
                DEEPSEEK_API_URL, 
                headers=self.headers, 
                json=payload, 
                stream=True,
                timeout=30
            )
            
            # 检查响应状态
            if response.status_code != 200:
                logger.error(f"API请求失败，状态码: {response.status_code}")
                return "", 0
            
            # 处理流式响应
            for chunk in response.iter_lines():
                if not chunk:
                    continue
                    
                decoded_chunk = chunk.decode('utf-8').strip()
                
                # 检查特殊标记，如[DONE]
                if decoded_chunk == "[DONE]":
                    logger.debug("接收到流结束标记: [DONE]")
                    continue
                    
                if not decoded_chunk.startswith("data: "):
                    continue
                    
                # 提取JSON部分
                json_str = decoded_chunk[6:]
                
                # 检查是否是空JSON或其他非标准格式
                if not json_str or json_str.isspace():
                    continue
                    
                try:
                    # 解析JSON数据
                    json_data = json.loads(json_str)
                    
                    # 提取内容
                    if "choices" in json_data and json_data["choices"]:
                        delta = json_data["choices"][0]["delta"]
                        
                        # 处理推理内容
                        reasoning_content = delta.get("reasoning_content", "") or ""
                        if reasoning_content:
                            print(reasoning_content, end='', flush=True)
                            reasoning_response += reasoning_content
                        
                        # 处理正式回复内容
                        content = delta.get("content", "") or ""
                        if content:
                            print(content, end='', flush=True)
                            ai_response += content
                            
                            # 发送给TTS处理
                            if content.strip():
                                self.response_queue.put(content)
                    
                    # 获取token统计
                    if "usage" in json_data:
                        total_tokens = json_data["usage"].get("total_tokens", 0)
                        
                except json.JSONDecodeError as e:
                    # 检查是否是已知的特殊消息格式
                    if "[DONE]" in json_str:
                        logger.debug(f"接收到包含[DONE]的消息: {json_str}")
                    else:
                        logger.debug(f"无法解析JSON: {json_str} - 错误: {e}")
                    continue
            
            # 标记流式响应结束
            self.response_queue.put(RESPONSE_END_MARKER)
            print('\n')
            
            return ai_response, total_tokens
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API请求异常: {e}")
            return "", 0
    
    def _manage_context_size(self, total_tokens):
        """管理对话上下文大小，防止过长"""
        if len(self.messages) <= 1 or total_tokens <= MAX_TOKENS_THRESHOLD:
            return
            
        # 移除较早的非系统消息以控制上下文大小
        removed = self.messages.pop(1)
        logger.warning(f"已移除历史记录: {removed}")
        
        # 如果仍然超过阈值，再移除一条
        if len(self.messages) > 1 and total_tokens > MAX_TOKENS_THRESHOLD:
            removed = self.messages.pop(1)
            logger.warning(f"已移除历史记录: {removed}")
    
    def ask(self, user_input):
        """
        向DeepSeek发送用户问题并获取回复
        
        参数:
            user_input: 用户输入文本
            
        返回:
            AI回复的文本
        """
        # 添加用户消息
        self.messages.append({"role": "user", "content": user_input})
        
        # 获取流式回复
        ai_response, total_tokens = self._stream_api_response()
        
        # 如果获取到有效回复
        if ai_response:
            # 添加AI回复到对话记录
            self.messages.append({"role": "assistant", "content": ai_response})
            
            # 管理上下文大小
            self._manage_context_size(total_tokens)
            
            return ai_response
        
        # 处理无回复的情况
        logger.error("未获取到AI回复")
        return "抱歉，我无法获取回复。请稍后重试。"
    
    def save(self):
        """保存当前对话记录到文件"""
        try:
            # 删除已存在的文件
            if os.path.exists(CONTEXT_FILE):
                os.remove(CONTEXT_FILE)
                
            # 写入新文件
            with open(CONTEXT_FILE, 'wb+') as f:
                pickle.dump(self.messages, f)
                
            logger.info("对话记录已保存")
            return True
            
        except Exception as e:
            logger.error(f"保存对话记录失败: {e}")
            return False
    
    def load(self):
        """从文件加载对话记录"""
        try:
            # 检查文件是否存在
            if os.path.exists(CONTEXT_FILE):
                with open(CONTEXT_FILE, "rb+") as f:
                    self.messages = pickle.load(f)
                logger.info("对话记录已加载")
                return True
            else:
                logger.info("未找到保存的对话记录，初始化新对话")
                self.initialize_system()
                return False
                
        except Exception as e:
            logger.error(f"加载对话记录失败: {e}")
            self.initialize_system()
            return False


# 创建全局DeepSeek对话实例
deepseek_chat = DeepSeekChat()

# 提供与原接口兼容的函数

def init_system():
    """初始化系统提示"""
    deepseek_chat.initialize_system()

def ask(user_input):
    """处理用户输入并获取回复"""
    return deepseek_chat.ask(user_input)

def save():
    """保存对话记录"""
    deepseek_chat.save()

def read():
    """读取对话记录"""
    deepseek_chat.load()

# 公开TTS管理器实例以保持兼容性
tts_manager = deepseek_chat.tts_manager
response_queue = deepseek_chat.response_queue


# 测试代码
if __name__ == "__main__":
    read()
    print("开始对话（输入\"结束对话\"退出）：")

    while True:
        user_input = input("用户: ").strip()
        tts_manager.stop_tts()
        
        if user_input == "" or user_input == "结束对话":
            print("对话结束。")
            save()
            break
            
        print("AI:", end=' ', flush=True)
        ask(user_input)