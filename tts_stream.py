import time
import threading
import pyaudio
from queue import Empty
from loguru import logger
import azure.cognitiveservices.speech as speechsdk
from const_config import azure_key

class TTSManager:
    """管理流式文本转语音处理"""
    
    def __init__(self, response_queue):
        """
        初始化TTS管理器
        
        参数:
            response_queue: 接收文本数据的队列
        """
        # 控制状态
        self.stop_event = threading.Event()
        self.tts_task = None
        self.response_queue = response_queue

        # 配置Azure TTS服务
        self._setup_azure_tts()
    
    def _setup_azure_tts(self):
        """配置Azure TTS服务"""
        # 创建语音配置
        self.speech_config = speechsdk.SpeechConfig(
            endpoint="wss://eastasia.tts.speech.microsoft.com/cognitiveservices/websocket/v2",
            subscription=azure_key
        )
        self.speech_config.speech_synthesis_voice_name = "zh-CN-XiaoxiaoNeural"

        # 创建自定义音频输出流
        self.custom_callback = self.CustomPushStreamCallback(self)
        self.audio_output_stream = speechsdk.audio.PushAudioOutputStream(self.custom_callback)
        self.audio_config = speechsdk.audio.AudioOutputConfig(stream=self.audio_output_stream)

        # 创建语音合成器
        self.speech_synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=self.speech_config,
            audio_config=self.audio_config
        )
        logger.debug("Azure TTS服务已配置")

    class CustomPushStreamCallback(speechsdk.audio.PushAudioOutputStreamCallback):
        """自定义音频输出流回调处理"""
        
        def __init__(self, tts_manager):
            """
            初始化回调处理器
            
            参数:
                tts_manager: 父TTS管理器实例
            """
            super().__init__()
            self.tts_manager = tts_manager
            
            # 初始化PyAudio
            self.pyaudio_instance = pyaudio.PyAudio()
            self.stream = self.pyaudio_instance.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                output=True,
                frames_per_buffer=16384
            )
            logger.debug("音频输出流已初始化")

        def write(self, buffer: memoryview) -> int:
            """
            处理音频数据写入
            
            参数:
                buffer: 要写入的音频数据
                
            返回:
                处理的字节数
            """
            if self.tts_manager.stop_event.is_set():
                logger.debug('音频输出已停止')
                return 0
                
            # 将音频数据写入输出流
            self.stream.write(buffer.tobytes())
            return len(buffer)

        def close(self):
            """关闭音频资源"""
            try:
                self.stream.stop_stream()
                self.stream.close()
                self.pyaudio_instance.terminate()
                logger.info("音频资源已释放")
            except Exception as e:
                logger.error(f"关闭音频资源失败: {e}")

    def stop_tts(self):
        """停止当前TTS播放"""
        logger.debug('正在停止TTS播放')
        
        # 停止语音合成
        self.speech_synthesizer.stop_speaking_async()
        
        # 设置停止标志并等待任务完成
        self.stop_event.set()
        if self.tts_task:
            self.tts_task.get()
            
        # 清除停止标志，为下次播放准备
        self.stop_event.clear()
        logger.debug('TTS播放已停止')

    def start_tts(self):
        """监听文本队列并进行流式TTS播放"""
        logger.info('流式TTS服务已启动')
        
        while True:
            # 检查队列是否有内容，避免忙等待
            if self.response_queue.empty():
                time.sleep(0.1)
                continue

            # 检查停止标志
            if self.stop_event.is_set():
                break

            # 创建流式TTS请求
            tts_request = speechsdk.SpeechSynthesisRequest(
                input_type=speechsdk.SpeechSynthesisRequestInputType.TextStream
            )
            self.tts_task = self.speech_synthesizer.speak_async(tts_request)

            # 流式处理文本
            self._process_text_stream(tts_request)
    
    def _process_text_stream(self, tts_request):
        """
        处理文本流并发送到TTS引擎
        
        参数:
            tts_request: TTS请求对象
        """
        while not self.stop_event.is_set():
            try:
                # 等待新的文本块，超时5秒
                text_chunk = self.response_queue.get(timeout=5)
                
                # 检查是否结束标记
                if text_chunk == "[END]":
                    logger.debug("收到结束标记，当前对话TTS完成")
                    break
                
                # 将文本块发送到TTS引擎
                tts_request.input_stream.write(text_chunk)
                
            except Empty:
                logger.debug("等待文本超时，结束当前TTS会话")
                break
            except Exception as e:
                logger.error(f"处理文本流时出错: {e}")
                break
                
        # 关闭输入流，完成当前语音合成
        tts_request.input_stream.close()
        logger.debug("TTS输入流已关闭")

