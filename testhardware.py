#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
硬件测试程序
用于测试连接到树莓派的LED、蜂鸣器、火焰传感器和烟雾传感器
"""

import RPi.GPIO as GPIO
import time
import sys

# 导入硬件配置
from hardware_config import PIN_LED, PIN_BUZZER, PIN_FLAME, PIN_SMOKE

# 全局变量
buzzer_pwm = None
PWM_FREQ = 2000  # PWM频率(Hz) - 蜂鸣器频率
flame_detected = False  # 火焰检测状态
smoke_detected = False  # 烟雾检测状态

def setup():
    """初始化GPIO设置"""
    global buzzer_pwm
    
    # 设置GPIO模式为BCM编号方式
    GPIO.setmode(GPIO.BCM)
    # 关闭警告信息
    GPIO.setwarnings(False)
    # 设置LED_PIN为输出模式
    GPIO.setup(PIN_LED, GPIO.OUT)
    # 设置BUZZER_PIN为输出模式
    GPIO.setup(PIN_BUZZER, GPIO.OUT)
    # 设置FLAME_PIN为输入模式，带有上拉电阻
    GPIO.setup(PIN_FLAME, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    # 设置SMOKE_PIN为输入模式，带有上拉电阻
    GPIO.setup(PIN_SMOKE, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    
    # 初始化蜂鸣器PWM
    buzzer_pwm = GPIO.PWM(PIN_BUZZER, PWM_FREQ)
    buzzer_pwm.start(0)  # 以0%占空比启动（静音）
    
    print(f"GPIO{PIN_LED}(LED)和GPIO{PIN_BUZZER}(蜂鸣器)已设置为输出模式")
    print(f"GPIO{PIN_FLAME}(火焰传感器)和GPIO{PIN_SMOKE}(烟雾传感器)已设置为输入模式")
    print(f"蜂鸣器PWM频率: {PWM_FREQ}Hz")

# LED控制函数
def blink_led(times=5, interval=0.5):
    """
    让LED闪烁指定次数
    
    参数:
        times: 闪烁次数
        interval: 闪烁间隔(秒)
    """
    for i in range(times):
        print(f"LED 开启 ({i+1}/{times})")
        GPIO.output(PIN_LED, GPIO.HIGH)  # 开启LED
        time.sleep(interval)
        
        print(f"LED 关闭 ({i+1}/{times})")
        GPIO.output(PIN_LED, GPIO.LOW)   # 关闭LED
        time.sleep(interval)

def turn_on_led():
    """开启LED"""
    GPIO.output(PIN_LED, GPIO.HIGH)
    print("LED已开启")

def turn_off_led():
    """关闭LED"""
    GPIO.output(PIN_LED, GPIO.LOW)
    print("LED已关闭")

# 蜂鸣器控制函数
def beep_buzzer(times=3, interval=0.3, volume=100):
    """
    让蜂鸣器发出指定次数的短促蜂鸣声
    
    参数:
        times: 蜂鸣次数
        interval: 蜂鸣间隔(秒)
        volume: 音量百分比(0-100)
    """
    for i in range(times):
        print(f"蜂鸣器 开启 ({i+1}/{times}) 音量: {volume}%")
        buzzer_pwm.ChangeDutyCycle(volume)  # 调整音量
        time.sleep(interval)
        
        print(f"蜂鸣器 关闭 ({i+1}/{times})")
        buzzer_pwm.ChangeDutyCycle(0)  # 关闭蜂鸣器
        time.sleep(interval)

def turn_on_buzzer(volume=100):
    """
    开启蜂鸣器
    
    参数:
        volume: 音量百分比(0-100)
    """
    buzzer_pwm.ChangeDutyCycle(volume)
    print(f"蜂鸣器已开启，音量: {volume}%")

def turn_off_buzzer():
    """关闭蜂鸣器"""
    buzzer_pwm.ChangeDutyCycle(0)
    print("蜂鸣器已关闭")

def set_buzzer_volume(volume):
    """
    设置蜂鸣器音量
    
    参数:
        volume: 音量百分比(0-100)
    """
    volume = max(0, min(100, volume))  # 确保音量在0-100范围内
    buzzer_pwm.ChangeDutyCycle(volume)
    print(f"蜂鸣器音量已设置为: {volume}%")

def volume_demo():
    """展示不同音量的蜂鸣器声音"""
    print("蜂鸣器音量演示...")
    volumes = [10, 30, 50, 70, 100]
    
    for vol in volumes:
        print(f"音量: {vol}%")
        buzzer_pwm.ChangeDutyCycle(vol)
        time.sleep(1)
        buzzer_pwm.ChangeDutyCycle(0)
        time.sleep(0.5)
    
    print("音量演示结束")

def tone_demo():
    """演示不同频率的蜂鸣器声音"""
    global buzzer_pwm
    
    print("蜂鸣器音调演示...")
    tones = [
        (262, "C4 - 中央C"),
        (294, "D4"),
        (330, "E4"),
        (349, "F4"),
        (392, "G4"),
        (440, "A4"),
        (494, "B4"),
        (523, "C5")
    ]
    
    for freq, name in tones:
        print(f"音调: {name} ({freq}Hz)")
        # 需要重新创建PWM实例来改变频率
        buzzer_pwm.stop()
        buzzer_pwm = GPIO.PWM(PIN_BUZZER, freq)
        buzzer_pwm.start(50)  # 以50%占空比启动
        time.sleep(0.5)
        buzzer_pwm.ChangeDutyCycle(0)
        time.sleep(0.2)
    
    # 恢复默认频率
    buzzer_pwm.stop()
    buzzer_pwm = GPIO.PWM(PIN_BUZZER, PWM_FREQ)
    buzzer_pwm.start(0)
    print("音调演示结束")

def alarm_pattern():
    """产生警报模式的声音和灯光效果"""
    print("启动警报模式...")
    for i in range(5):
        # 开启LED和蜂鸣器
        GPIO.output(PIN_LED, GPIO.HIGH)
        buzzer_pwm.ChangeDutyCycle(70)
        time.sleep(0.2)
        
        # 关闭蜂鸣器
        buzzer_pwm.ChangeDutyCycle(0)
        time.sleep(0.1)
        
        # 开启蜂鸣器（不同音量）
        buzzer_pwm.ChangeDutyCycle(100)
        time.sleep(0.2)
        
        # 关闭LED和蜂鸣器
        GPIO.output(PIN_LED, GPIO.LOW)
        buzzer_pwm.ChangeDutyCycle(0)
        time.sleep(0.5)
    
    print("警报模式结束")

def cleanup():
    """清理GPIO资源"""
    GPIO.output(PIN_LED, GPIO.LOW)  # 确保LED关闭
    if buzzer_pwm:
        buzzer_pwm.stop()  # 停止PWM
    GPIO.cleanup()
    print("GPIO资源已释放")

def interactive_mode():
    """交互模式，允许用户控制LED和蜂鸣器"""
    print("\n=== 硬件交互控制模式 ===")
    print("命令列表:")
    print("  1 - 开启LED")
    print("  2 - 关闭LED")
    print("  3 - LED闪烁")
    print("  4 - 开启蜂鸣器 [音量0-100]")
    print("  5 - 关闭蜂鸣器")
    print("  6 - 蜂鸣器短促蜂鸣 [次数] [音量0-100]")
    print("  7 - 设置蜂鸣器音量 [音量0-100]")
    print("  8 - 蜂鸣器音量演示")
    print("  9 - 蜂鸣器音调演示")
    print(" 10 - 警报模式（LED和蜂鸣器协同工作）")
    print(" 11 - 读取火焰传感器当前状态")
    print(" 12 - 监控火焰传感器 [持续时间(秒)]")
    print(" 13 - 启动火焰报警模式（检测到火焰时触发警报）")
    print(" 14 - 读取烟雾传感器当前状态")
    print(" 15 - 监控烟雾传感器 [持续时间(秒)]")
    print(" 16 - 启动烟雾报警模式（检测到烟雾时触发警报）")
    print(" 17 - 启动综合报警模式（检测到火焰或烟雾时触发警报）")
    print("  0 - 退出程序")
    
    try:
        while True:
            cmd_input = input("\n请输入命令编号: ").strip()
            cmd = cmd_input.split()[0] if cmd_input else ""
            
            if cmd == "1":
                turn_on_led()
            elif cmd == "2":
                turn_off_led()
            elif cmd == "3":
                count = input("请输入闪烁次数[默认5]: ").strip()
                count = int(count) if count.isdigit() else 5
                blink_led(count)
            elif cmd == "4":
                parts = cmd_input.split()
                if len(parts) > 1 and parts[1].isdigit():
                    volume = int(parts[1])
                else:
                    volume = input("请输入音量(0-100)[默认100]: ").strip()
                    volume = int(volume) if volume.isdigit() else 100
                turn_on_buzzer(volume)
            elif cmd == "5":
                turn_off_buzzer()
            elif cmd == "6":
                parts = cmd_input.split()
                count = None
                volume = None
                
                if len(parts) > 1 and parts[1].isdigit():
                    count = int(parts[1])
                if len(parts) > 2 and parts[2].isdigit():
                    volume = int(parts[2])
                    
                if count is None:
                    count_input = input("请输入蜂鸣次数[默认3]: ").strip()
                    count = int(count_input) if count_input.isdigit() else 3
                
                if volume is None:
                    volume_input = input("请输入音量(0-100)[默认100]: ").strip()
                    volume = int(volume_input) if volume_input.isdigit() else 100
                
                beep_buzzer(count, 0.3, volume)
            elif cmd == "7":
                parts = cmd_input.split()
                if len(parts) > 1 and parts[1].isdigit():
                    volume = int(parts[1])
                else:
                    volume = input("请输入音量(0-100): ").strip()
                    volume = int(volume) if volume.isdigit() else 0
                set_buzzer_volume(volume)
            elif cmd == "8":
                volume_demo()
            elif cmd == "9":
                tone_demo()
            elif cmd == "10":
                alarm_pattern()
            elif cmd == "11":
                flame_state = read_flame_sensor()
                print(f"火焰传感器状态: {'检测到火焰！' if flame_state else '未检测到火焰'}")
            elif cmd == "12":
                parts = cmd_input.split()
                duration = None
                if len(parts) > 1 and parts[1].isdigit():
                    duration = int(parts[1])
                else:
                    duration_input = input("请输入监控持续时间(秒)[默认10]: ").strip()
                    duration = int(duration_input) if duration_input.isdigit() else 10
                monitor_flame_sensor(duration)
            elif cmd == "13":
                flame_alarm_mode()
            elif cmd == "14":
                smoke_state = read_smoke_sensor()
                print(f"烟雾传感器状态: {'检测到烟雾！' if smoke_state else '未检测到烟雾'}")
            elif cmd == "15":
                parts = cmd_input.split()
                duration = None
                if len(parts) > 1 and parts[1].isdigit():
                    duration = int(parts[1])
                else:
                    duration_input = input("请输入监控持续时间(秒)[默认10]: ").strip()
                    duration = int(duration_input) if duration_input.isdigit() else 10
                monitor_smoke_sensor(duration)
            elif cmd == "16":
                smoke_alarm_mode()
            elif cmd == "17":
                combined_alarm_mode()
            elif cmd == "0":
                break
            else:
                print("未知命令，请重试")
    except KeyboardInterrupt:
        print("\n程序被用户中断")

# 火焰传感器函数
def read_flame_sensor():
    """
    读取火焰传感器状态
    
    数字火焰传感器DO输出：
    - 低电平(0): 检测到火焰
    - 高电平(1): 未检测到火焰
    
    返回:
        布尔值，True表示检测到火焰，False表示未检测到
    """
    try:
        # 读取传感器状态（低电平表示检测到火焰）
        state = not GPIO.input(PIN_FLAME)
        return state
    except Exception as e:
        print(f"读取火焰传感器失败: {e}")
        return False

def monitor_flame_sensor(duration=10, interval=0.5):
    """
    监控火焰传感器一段时间
    
    参数:
        duration: 监控持续时间(秒)
        interval: 读取间隔(秒)
    """
    print(f"开始监控火焰传感器，持续{duration}秒...")
    start_time = time.time()
    
    try:
        while time.time() - start_time < duration:
            flame_detected = read_flame_sensor()
            status = "检测到火焰！" if flame_detected else "未检测到火焰"
            
            # 如果检测到火焰，点亮LED和蜂鸣器警报
            if flame_detected:
                GPIO.output(PIN_LED, GPIO.HIGH)  # 开启LED
                buzzer_pwm.ChangeDutyCycle(50)   # 开启蜂鸣器
            else:
                GPIO.output(PIN_LED, GPIO.LOW)   # 关闭LED
                buzzer_pwm.ChangeDutyCycle(0)    # 关闭蜂鸣器
                
            print(f"火焰传感器状态: {status}")
            time.sleep(interval)
        
        # 确保结束时LED和蜂鸣器关闭
        GPIO.output(PIN_LED, GPIO.LOW)
        buzzer_pwm.ChangeDutyCycle(0)
        
    except KeyboardInterrupt:
        print("\n监控被用户中断")
        # 确保LED和蜂鸣器关闭
        GPIO.output(PIN_LED, GPIO.LOW)
        buzzer_pwm.ChangeDutyCycle(0)
    
    print("火焰传感器监控结束")

def flame_alarm_mode():
    """火焰报警模式 - 持续监控火焰传感器，检测到火焰时触发警报"""
    print("启动火焰报警模式...")
    print("按Ctrl+C退出")
    
    try:
        while True:
            flame_detected = read_flame_sensor()
            
            if flame_detected:
                print("警报：检测到火焰！")
                for _ in range(3):  # 触发3次警报
                    GPIO.output(PIN_LED, GPIO.HIGH)  # 开启LED
                    buzzer_pwm.ChangeDutyCycle(70)   # 开启蜂鸣器
                    time.sleep(0.2)
                    buzzer_pwm.ChangeDutyCycle(0)    # 暂停蜂鸣器
                    time.sleep(0.1)
                    buzzer_pwm.ChangeDutyCycle(100)  # 开启蜂鸣器（高音量）
                    time.sleep(0.2)
                    GPIO.output(PIN_LED, GPIO.LOW)   # 关闭LED
                    buzzer_pwm.ChangeDutyCycle(0)    # 关闭蜂鸣器
                    time.sleep(0.1)
            else:
                # 未检测到火焰时短暂休眠
                time.sleep(0.3)
    
    except KeyboardInterrupt:
        print("\n火焰报警模式被用户中断")
        # 确保LED和蜂鸣器关闭
        GPIO.output(PIN_LED, GPIO.LOW)
        buzzer_pwm.ChangeDutyCycle(0)
    
    print("火焰报警模式结束")

# 烟雾传感器函数
def read_smoke_sensor():
    """
    读取烟雾传感器状态
    
    数字烟雾传感器DO输出：
    - 低电平(0): 检测到烟雾
    - 高电平(1): 未检测到烟雾
    
    返回:
        布尔值，True表示检测到烟雾，False表示未检测到
    """
    try:
        # 读取传感器状态（低电平表示检测到烟雾）
        state = not GPIO.input(PIN_SMOKE)
        return state
    except Exception as e:
        print(f"读取烟雾传感器失败: {e}")
        return False

def monitor_smoke_sensor(duration=10, interval=0.5):
    """
    监控烟雾传感器一段时间
    
    参数:
        duration: 监控持续时间(秒)
        interval: 读取间隔(秒)
    """
    print(f"开始监控烟雾传感器，持续{duration}秒...")
    start_time = time.time()
    
    try:
        while time.time() - start_time < duration:
            smoke_detected = read_smoke_sensor()
            status = "检测到烟雾！" if smoke_detected else "未检测到烟雾"
            
            # 如果检测到烟雾，点亮LED和蜂鸣器警报
            if smoke_detected:
                GPIO.output(PIN_LED, GPIO.HIGH)  # 开启LED
                buzzer_pwm.ChangeDutyCycle(50)   # 开启蜂鸣器
            else:
                GPIO.output(PIN_LED, GPIO.LOW)   # 关闭LED
                buzzer_pwm.ChangeDutyCycle(0)    # 关闭蜂鸣器
                
            print(f"烟雾传感器状态: {status}")
            time.sleep(interval)
        
        # 确保结束时LED和蜂鸣器关闭
        GPIO.output(PIN_LED, GPIO.LOW)
        buzzer_pwm.ChangeDutyCycle(0)
        
    except KeyboardInterrupt:
        print("\n监控被用户中断")
        # 确保LED和蜂鸣器关闭
        GPIO.output(PIN_LED, GPIO.LOW)
        buzzer_pwm.ChangeDutyCycle(0)
    
    print("烟雾传感器监控结束")

def smoke_alarm_mode():
    """烟雾报警模式 - 持续监控烟雾传感器，检测到烟雾时触发警报"""
    print("启动烟雾报警模式...")
    print("按Ctrl+C退出")
    
    try:
        while True:
            smoke_detected = read_smoke_sensor()
            
            if smoke_detected:
                print("警报：检测到烟雾！")
                for _ in range(3):  # 触发3次警报
                    GPIO.output(PIN_LED, GPIO.HIGH)  # 开启LED
                    buzzer_pwm.ChangeDutyCycle(70)   # 开启蜂鸣器
                    time.sleep(0.2)
                    buzzer_pwm.ChangeDutyCycle(0)    # 暂停蜂鸣器
                    time.sleep(0.1)
                    buzzer_pwm.ChangeDutyCycle(100)  # 开启蜂鸣器（高音量）
                    time.sleep(0.2)
                    GPIO.output(PIN_LED, GPIO.LOW)   # 关闭LED
                    buzzer_pwm.ChangeDutyCycle(0)    # 关闭蜂鸣器
                    time.sleep(0.1)
            else:
                # 未检测到烟雾时短暂休眠
                time.sleep(0.3)
    
    except KeyboardInterrupt:
        print("\n烟雾报警模式被用户中断")
        # 确保LED和蜂鸣器关闭
        GPIO.output(PIN_LED, GPIO.LOW)
        buzzer_pwm.ChangeDutyCycle(0)
    
    print("烟雾报警模式结束")

def combined_alarm_mode():
    """综合报警模式 - 持续监控火焰和烟雾传感器，检测到任一情况时触发警报"""
    print("启动综合报警模式（火焰+烟雾）...")
    print("按Ctrl+C退出")
    
    try:
        while True:
            flame_detected = read_flame_sensor()
            smoke_detected = read_smoke_sensor()
            
            if flame_detected or smoke_detected:
                alert_type = []
                if flame_detected:
                    alert_type.append("火焰")
                if smoke_detected:
                    alert_type.append("烟雾")
                
                alert_msg = "、".join(alert_type)
                print(f"警报：检测到{alert_msg}！")
                
                for _ in range(3):  # 触发3次警报
                    GPIO.output(PIN_LED, GPIO.HIGH)  # 开启LED
                    buzzer_pwm.ChangeDutyCycle(70)   # 开启蜂鸣器
                    time.sleep(0.2)
                    buzzer_pwm.ChangeDutyCycle(0)    # 暂停蜂鸣器
                    time.sleep(0.1)
                    buzzer_pwm.ChangeDutyCycle(100)  # 开启蜂鸣器（高音量）
                    time.sleep(0.2)
                    GPIO.output(PIN_LED, GPIO.LOW)   # 关闭LED
                    buzzer_pwm.ChangeDutyCycle(0)    # 关闭蜂鸣器
                    time.sleep(0.1)
            else:
                # 未检测到异常时短暂休眠
                time.sleep(0.3)
    
    except KeyboardInterrupt:
        print("\n综合报警模式被用户中断")
        # 确保LED和蜂鸣器关闭
        GPIO.output(PIN_LED, GPIO.LOW)
        buzzer_pwm.ChangeDutyCycle(0)
    
    print("综合报警模式结束")

if __name__ == "__main__":
    try:
        setup()
        
        if len(sys.argv) > 1:
            # 命令行参数模式
            cmd = sys.argv[1].lower()
            if cmd == "1" or cmd == "led_on":
                turn_on_led()
            elif cmd == "2" or cmd == "led_off":
                turn_off_led()
            elif cmd == "3" or cmd == "led_blink":
                count = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 5
                blink_led(count)
            elif cmd == "4" or cmd == "buz_on":
                volume = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 100
                turn_on_buzzer(volume)
            elif cmd == "5" or cmd == "buz_off":
                turn_off_buzzer()
            elif cmd == "6" or cmd == "beep":
                count = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 3
                volume = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3].isdigit() else 100
                beep_buzzer(count, 0.3, volume)
            elif cmd == "7" or cmd == "volume":
                volume = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 50
                set_buzzer_volume(volume)
            elif cmd == "8" or cmd == "vol_demo":
                volume_demo()
            elif cmd == "9" or cmd == "tone_demo":
                tone_demo()
            elif cmd == "10" or cmd == "alarm":
                alarm_pattern()
            elif cmd == "11" or cmd == "flame":
                flame_state = read_flame_sensor()
                print(f"火焰传感器状态: {'检测到火焰！' if flame_state else '未检测到火焰'}")
            elif cmd == "12" or cmd == "flame_mon":
                duration = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 10
                monitor_flame_sensor(duration)
            elif cmd == "13" or cmd == "flame_alarm":
                flame_alarm_mode()
            elif cmd == "14" or cmd == "smoke":
                smoke_state = read_smoke_sensor()
                print(f"烟雾传感器状态: {'检测到烟雾！' if smoke_state else '未检测到烟雾'}")
            elif cmd == "15" or cmd == "smoke_mon":
                duration = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 10
                monitor_smoke_sensor(duration)
            elif cmd == "16" or cmd == "smoke_alarm":
                smoke_alarm_mode()
            elif cmd == "17" or cmd == "combined_alarm":
                combined_alarm_mode()
            else:
                print(f"未知命令: {cmd}")
                print("可用命令: 1/led_on, 2/led_off, 3/led_blink, 4/buz_on [音量], 5/buz_off, 6/beep [次数] [音量], 7/volume [音量], 8/vol_demo, 9/tone_demo, 10/alarm, 11/flame, 12/flame_mon [时间], 13/flame_alarm, 14/smoke, 15/smoke_mon [时间], 16/smoke_alarm, 17/combined_alarm")
        else:
            # 无参数，进入交互模式
            print("硬件测试程序")
            print(f"LED连接到GPIO{PIN_LED}，蜂鸣器连接到GPIO{PIN_BUZZER}")
            print(f"火焰传感器连接到GPIO{PIN_FLAME}，烟雾传感器连接到GPIO{PIN_SMOKE}")
            
            # 进入交互模式
            interactive_mode()
            
    except Exception as e:
        print(f"发生错误: {e}")
    finally:
        cleanup()
        print("程序已退出")
