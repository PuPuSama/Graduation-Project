# 用到的端口 3306 mysql 3300 音乐接口 5000 网络交互 6666 udp服务

use_deepseek=True
sfapikey='sk-fvkttilwbytxgnmjzmwfwyltixywtgliuzubzawiohuikpfa'

chat_or_standard=True #采用聊天模式还是标准模式（家庭助手），True为聊天模式（采用流式），详见 prompt_and_deal.py
#切换模式后需删除 message.data文件（如有），否则会导致对话混乱

########语音服务(TTS and STT)##########
use_online_recognize=True #系统现在仅支持线上语音识别服务，离线识别功能已移除
azure_key='2jTGJMnQmakNysRaNfckH8lazl5OL7BVgSVIV37MEtGzuhpPjBmNJQQJ99BCAC3pKaRXJ3w3AAAYACOGscFz'   #使用线上语音识别需填写 Azrue key


#########语音唤醒模块###########
porcupine_enable=True   #是否加载porcupine模块 (推荐，跨平台)
porcupine_key="S86djrdnd5xbeM8ezjjPJyuygJ9KgFz+roS8tGEKR+WqQb13KRk+tg=="#需要填写密钥
porcupinepath="/home/pi/Graduation-Project/Porcupine" #porcupine位置
porcupine_keyword_name="蛋卷_zh_raspberry-pi_v3_0_0.ppn" #唤醒词文件名
porcupine_model_path="/home/pi/Graduation-Project/Porcupine/porcupine_params_zh.pv" #模型文件位置

##############
gpio_wake_enable=False  #按键唤醒，如果相应引脚接有外设的情况下开启