#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
硬件配置模块
集中管理所有硬件设备的GPIO引脚分配和其他配置参数
这是一个单一真实来源(single source of truth)，避免不同模块使用不同的引脚定义
"""

# GPIO引脚定义 (BCM模式)
# 输出设备
PIN_LED = 17        # LED灯引脚 (使用PWM控制)
PIN_BUZZER = 18     # 蜂鸣器引脚

# 输入设备
PIN_DHT11 = 4       # DHT11温湿度传感器引脚
PIN_FLAME = 12      # 火焰传感器引脚 (预留)
PIN_SMOKE = 16      # 烟雾传感器引脚 (预留)

# 设备配置参数
LED_PWM_FREQ = 100  # LED PWM频率 (Hz)
SENSOR_INTERVAL = 300  # 传感器数据采集间隔 (秒)

# MQTT服务器配置
MQTT_BROKER = "localhost"  # MQTT服务器地址
MQTT_PORT = 1883           # MQTT服务器端口
MQTT_TOPIC_SENSOR = "home/sensors"  # 传感器数据主题
MQTT_TOPIC_CONTROL = "home/control"  # 设备控制主题
MQTT_USERNAME = ""         # MQTT用户名 (如需认证)
MQTT_PASSWORD = ""         # MQTT密码 (如需认证) 