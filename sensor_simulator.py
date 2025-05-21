# -*- coding: utf-8 -*-
"""
传感器模拟器
用于生成模拟的温湿度、火焰、烟雾传感器数据以及蜂鸣器状态
"""

import random
import time
from datetime import datetime

class SensorSimulator:
    """模拟多种传感器数据的类"""
    
    def __init__(self, temp_range=(15, 40), humidity_range=(30, 90)):
        """
        初始化传感器模拟器
        
        参数:
            temp_range (tuple): 温度范围，单位摄氏度，默认(15, 40)
            humidity_range (tuple): 湿度范围，单位%，默认(30, 90)
        """
        self.temp_range = temp_range
        self.humidity_range = humidity_range
        # 记录上一次的值，使模拟更真实（避免大幅度波动）
        self.last_temp = random.uniform(*temp_range)
        self.last_humidity = random.uniform(*humidity_range)
        self.flame_detected = False
        self.smoke_level = 0
        self.buzzer_active = False
    
    def get_temperature(self):
        """
        获取模拟的温度数据
        
        返回:
            float: 模拟的温度值，单位摄氏度
        """
        # 在上次温度的基础上小幅度变化，使数据更真实
        change = random.uniform(-0.5, 0.5)
        new_temp = self.last_temp + change
        
        # 确保温度在设定范围内
        if new_temp < self.temp_range[0]:
            new_temp = self.temp_range[0]
        elif new_temp > self.temp_range[1]:
            new_temp = self.temp_range[1]
            
        self.last_temp = new_temp
        return round(new_temp, 1)
    
    def get_humidity(self):
        """
        获取模拟的湿度数据
        
        返回:
            float: 模拟的湿度值，单位%
        """
        # 在上次湿度的基础上小幅度变化
        change = random.uniform(-2, 2)
        new_humidity = self.last_humidity + change
        
        # 确保湿度在设定范围内
        if new_humidity < self.humidity_range[0]:
            new_humidity = self.humidity_range[0]
        elif new_humidity > self.humidity_range[1]:
            new_humidity = self.humidity_range[1]
            
        self.last_humidity = new_humidity
        return round(new_humidity, 1)
    
    def get_flame_sensor(self):
        """
        获取模拟的火焰传感器数据
        
        返回:
            bool: True表示检测到火焰，False表示未检测到
        """
        # 偶尔模拟火焰事件，概率为1%
        if random.random() < 0.01:
            self.flame_detected = True
        # 如果已经检测到火焰，有一定概率恢复正常
        elif self.flame_detected and random.random() < 0.2:
            self.flame_detected = False
            
        return self.flame_detected
    
    def get_smoke_sensor(self):
        """
        获取模拟的烟雾传感器数据
        
        返回:
            int: 烟雾浓度，范围0-100，0表示无烟雾
        """
        # 如果检测到火焰，烟雾浓度可能会增加
        if self.flame_detected and self.smoke_level < 80:
            increase = random.randint(5, 15)
            self.smoke_level = min(100, self.smoke_level + increase)
        # 否则，烟雾浓度可能会逐渐降低
        elif self.smoke_level > 0:
            decrease = random.randint(1, 5)
            self.smoke_level = max(0, self.smoke_level - decrease)
        # 偶尔随机生成烟雾
        elif random.random() < 0.02:
            self.smoke_level = random.randint(10, 30)
            
        return self.smoke_level
    
    def get_buzzer_status(self):
        """
        获取模拟的蜂鸣器状态
        
        返回:
            bool: True表示蜂鸣器激活，False表示未激活
        """
        # 当检测到火焰或烟雾浓度高时，蜂鸣器激活
        if self.flame_detected or self.smoke_level > 50:
            self.buzzer_active = True
        else:
            self.buzzer_active = False
            
        return self.buzzer_active
    
    def get_all_sensor_data(self):
        """
        获取所有传感器的数据
        
        返回:
            dict: 包含所有传感器数据的字典
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return {
            "timestamp": timestamp,
            "temperature": self.get_temperature(),
            "humidity": self.get_humidity(),
            "flame_detected": self.get_flame_sensor(),
            "smoke_level": self.get_smoke_sensor(),
            "buzzer_active": self.get_buzzer_status()
        }

# 演示使用方法
if __name__ == "__main__":
    # 创建传感器模拟器实例
    simulator = SensorSimulator()
    
    print("传感器模拟器启动，按Ctrl+C停止...")
    try:
        # 循环生成传感器数据
        while True:
            data = simulator.get_all_sensor_data()
            print(f"时间: {data['timestamp']}")
            print(f"温度: {data['temperature']}°C")
            print(f"湿度: {data['humidity']}%")
            print(f"火焰: {'检测到' if data['flame_detected'] else '未检测'}")
            print(f"烟雾: {data['smoke_level']}%")
            print(f"蜂鸣器: {'激活' if data['buzzer_active'] else '未激活'}")
            print("-" * 30)
            time.sleep(2)  # 每2秒更新一次
    except KeyboardInterrupt:
        print("\n传感器模拟器已停止") 