#coding=utf-8
import requests
import json
import arcade
import time
import re
from pydub import AudioSegment
import tts
# import dealCookie
from play import play
from config import config
from const_config import qqid
from loguru import logger
header={"Connection":"close"}
musicsound=None
musicplayer=None
interrupted_music=False
search=False
cookiewrong=False
startagain=False
words=''
music=requests.session()
advice = []
order=0

# 音乐命令配置
MUSIC_COMMANDS = {
    # 播放/继续播放音乐
    'play': {
        'patterns': [
            r'^播放音乐[。]?$',
            r'^播放歌曲[。]?$',
            r'^放[一首]*音乐[。]?$',
            r'^来[一首]*音乐[。]?$',
            r'^来[一首]*歌[。]?$',
            r'^放[一首]*歌[。]?$',
            r'^播放推荐音乐[。]?$',
            r'^播放日推[。]?$',
            r'继续播放'
        ],
        'action': 'play_music'
    },
    
    # 搜索并播放指定音乐
    'search': {
        'patterns': [
            r'^播放音乐(.+)[。]?$',
            r'^搜索音乐(.+)[。]?$',
            r'^搜索歌曲(.+)[。]?$',
            r'^播放歌曲(.+)[。]?$',
            r'^播放(.+)的歌[。]?$',
            r'^来一首(.+)的歌[。]?$',
            r'^搜索(.+)的歌[。]?$',
            r'^放一首(.+)的歌[。]?$',
        ],
        'action': 'search_music'
    },
    
    # 播放下一首
    'next': {
        'patterns': [
            r'^下一首[。]?$',
            r'^下一首音乐[。]?$',
            r'播放.*下[一]*首',
            r'切换.*下[一]*首'
        ],
        'action': 'next_music'
    },
    
    # 停止播放
    'stop': {
        'patterns': [
            r'停止.*音乐',
            r'暂停.*音乐',
            r'关闭.*音乐',
            r'停止.*播放',
            r'暂停.*播放',
            r'关闭.*播放',
            r'停止.*歌曲',
            r'暂停.*歌曲',
            r'关闭.*歌曲',
            r'^静音[。]?$',
            r'音乐关了'
        ],
        'action': 'stop_music'
    },
    
    # 调整音量
    'volume_adjust': {
        'patterns': [
            r'调整.*声音.*(\d+)',
            r'调整.*音量.*(\d+)'
        ],
        'action': 'adjust_volume'
    },
    
    # 增大音量
    'volume_up': {
        'patterns': [
            r'声音.*大一点',
            r'声音.*调大',
            r'声音.*增加',
            r'声音.*提高',
            r'音量.*大一点',
            r'音量.*调大',
            r'音量.*增加',
            r'音量.*提高'
        ],
        'action': 'volume_up'
    },
    
    # 减小音量
    'volume_down': {
        'patterns': [
            r'声音.*小一点',
            r'声音.*调小',
            r'声音.*减小',
            r'声音.*降低',
            r'音量.*小一点',
            r'音量.*调小',
            r'音量.*减小',
            r'音量.*降低'
        ],
        'action': 'volume_down'
    }
}

def match_command(text):
    """
    匹配用户输入与预定义的命令模式
    返回匹配的命令类型和提取的参数
    """
    for cmd_type, cmd_config in MUSIC_COMMANDS.items():
        for pattern in cmd_config['patterns']:
            match = re.search(pattern, text)
            if match:
                # 如果有捕获组，提取参数
                params = match.groups() if match.groups() else None
                return cmd_config['action'], params
    
    # 没有匹配任何命令
    return None, None

def process_search_text(text):
    """处理搜索关键词，清理和格式化"""
    if not text:
        return ""
        
    # 移除句尾的句号
    if text[-1] == '。':
        text = text[:-1]
    
    # 移除开头的逗号
    if text and text[0] == '，':
        text = text[1:]
    
    # 处理"歌手的歌曲"格式
    if '歌手' in text:
        text = " ".join(text.split('的', 1))
    
    return text.strip()

def play_music_action():
    """播放音乐动作"""
    play('Sound/musicprepare.wav')
    music_en()
    logger.info('开始播放音乐')
    return True

def search_music_action(params):
    """搜索并播放指定音乐"""
    global interrupted_music, search, words, startagain
    
    try:
        # 提取搜索关键词
        search_text = params[0] if params else ""
        words = process_search_text(search_text)
        
        if not words:
            logger.warning('搜索关键词为空')
            return True
            
        logger.info(f'搜索音乐：{words}')
        interrupted_music = True
        search = True
        startagain = True
        music_en()
        return True
    except Exception as e:
        logger.error(f'处理搜索关键词时出错: {e}')
        return True

def next_music_action():
    """播放下一首音乐"""
    global interrupted_music, startagain
    interrupted_music = True
    startagain = True
    logger.info('切换到下一首音乐')
    return True

def stop_music_action():
    """停止播放音乐"""
    music_off()
    logger.info('停止播放音乐')
    return True

def adjust_volume_action(params):
    """根据指定值调整音量"""
    try:
        if params and params[0]:
            volume_value = float(params[0]) / 100
            # 确保音量在有效范围内
            volume_value = max(0.0, min(1.0, volume_value))
            config.set(music_volume=volume_value)
            logger.info(f'音量已调整为: {volume_value * 100}%')
        return True
    except Exception as e:
        logger.error(f'调整音量时出错: {e}')
        return True

def volume_up_action():
    """增大音量"""
    current_volume = config.get("music_volume")
    new_volume = min(1.0, current_volume + 0.1)  # 确保不超过1.0
    config.set(music_volume=new_volume)
    logger.info(f'音量已增大至: {new_volume:.1f}')
    return True

def volume_down_action():
    """减小音量"""
    current_volume = config.get("music_volume")
    new_volume = max(0.0, current_volume - 0.1)  # 确保不低于0.0
    config.set(music_volume=new_volume)
    logger.info(f'音量已减小至: {new_volume:.1f}')
    return True

def musicdetect(text):
    """
    检测并处理音乐相关的语音命令
    """
    global interrupted_music, words, search, startagain
    
    # 匹配命令
    action, params = match_command(text)
    
    # 如果没有匹配到命令，返回False
    if not action:
        return False
    
    # 根据不同动作执行相应的处理函数
    if action == 'play_music':
        return play_music_action()
    elif action == 'search_music':
        return search_music_action(params)
    elif action == 'next_music':
        return next_music_action()
    elif action == 'stop_music':
        return stop_music_action()
    elif action == 'adjust_volume':
        return adjust_volume_action(params)
    elif action == 'volume_up':
        return volume_up_action()
    elif action == 'volume_down':
        return volume_down_action()
    
    # 默认返回False，表示没有处理任何命令
    return False

def music_get(url, headers):
    for _ in range(2):
        try:
            r = music.get(url, headers=headers, timeout=10)
            return r
        except Exception as e:
            logger.warning(e)
            time.sleep(5)
    play('Sound/urlwrong.wav')
    return False

# def get_source_cookie():
#     # print('stop in get source cookie')
#     # return
#     print('start get source cookie')
#     dealCookie.get_cookie()
#     print('complete')

# def set_cookie():

#     get_source_cookie()
#     with open('cookie.txt', 'r') as f:
#         cookie = f.read()
#         f.close()
#     cookiejson = {'data': cookie}
#     #print('cookie is', cookie)
#     print('start set new cookie')
#     headers = {"content-type": 'application/json', 'Connection': 'close'}
#     r = requests.post(url='http://127.0.0.1:3300/user/setCookie', json=cookiejson, headers=headers)
#     r.close()

def get_cookie():
    global cookiewrong,startagain
    with open('cookie.txt', 'r') as f:
        cookie = f.read()
        f.close()
    cookiejson = {'data': cookie}
    logger.info('start set cookie')
    headers = {"content-type": 'application/json', 'Connection': 'close'}
    r = requests.post(url='http://127.0.0.1:3300/user/setCookie', json=cookiejson, headers=headers)
    r.close()
    if cookie_check():
        cookiewrong = False
        return True
    else:
        # play('Sound/dealcookie.wav')
        # set_cookie()
        # play('Sound/dealcookieok.wav')
        # if not cookie_check():
        #     print('source cookie error')# 获取资源出现错误,请检查cookie
        #     if cookiewrong is False:
        #         cookiewrong=True
        #         startagain=False
        #     return False
        # else:
        #     return True
        return False

def cookie_check():
    global cookiewrong,startagain
    r=music_get(f'http://127.0.0.1:3300/user/getCookie?id={qqid}',headers=header)
    if  r is False:
        logger.error('cookie_get wrong ,check if service on ,return')
        cookiewrong=True
        startagain=False
        return False
    for cookie in r.cookies:
        if cookie.name == 'qm_keyst':
            if cookie.expires < int(time.time()):
                logger.info('need update cookie')
                return False
            else:
                logger.info('cookie is normal')
                return True
    return False

def get_advice_list():

    if not cookie_check():
        if not get_cookie():
            logger.error('cookie wrong , stop from get_adv_list')
            return

    r=music_get('http://127.0.0.1:3300/recommend/daily',headers=header)
    if  r is False:
        logger.error('cannot get (request) ,return')
        return
    data=json.loads(r.text)
    for i in range(len(data['data']['songlist'])):
        if data['data']['songlist'][i]['pay']['payplay']==0:
            advice.append({'songname':data['data']['songlist'][i]['songname'],'singer':data['data']['songlist'][i]['singer'][0]['name'],'songmid':data['data']['songlist'][i]['songmid']})
    r.close()
    logger.info(f'advice_list: {advice}')

def get_radio_list():

    if not cookie_check():
        if not get_cookie():
            logger.error('cookie wrong , stop from get_adv_list')
            return

    r=music_get('http://127.0.0.1:3300/radio?id=101',headers=header)
    if  r is False:
        logger.error('cannot get (request) ,return')
        return
    data=json.loads(r.text)
    try:
        for i in range(len(data['data']['tracks'])):
            if data['data']['tracks'][i]['pay']['pay_play']==0:
                item={'songname':data['data']['tracks'][i]['name'],'singer':data['data']['tracks'][i]['singer'][0]['name'],'songmid':data['data']['tracks'][i]['mid']}
                advice.append(item)
                logger.info(item)
    except Exception as e:
        logger.warning(e)
        return
    #print('advice_list:',advice)
    # r.close()
    # music.close()

def get_search_song(words):
    global interrupted_music, search
    interrupted_music = True
    search = True
    r = music_get(f'http://127.0.0.1:3300/search/quick?key={words}',headers=header)
    if  r is False:
        logger.error('cannot get (request) ,return')
        return
    data = json.loads(r.text)
    for i in range(len(data['data']['song']['itemlist'])):
        logger.info(i)
        r=music_get(f"http://127.0.0.1:3300/song/urls?id={data['data']['song']['itemlist'][i]['mid']}",headers=header)
        r.close()
        if  r is False:
            logger.error('cannot get (request) ,return')
            return
        if json.loads(r.text)['data']!={}:
            return [data['data']['song']['itemlist'][i]['mid'],data['data']['song']['itemlist'][i]['name'],data['data']['song']['itemlist'][i]['singer']]
        else:
            logger.info('find next')
    #interrupted_music=False
    #search=False
    #play(Musicnotfound.wav')
    #return False
    music.close()
    return get_search_song_deep(words)

def get_search_song_deep(words):
    global interrupted_music,search
    logger.info('start deep search')
    r = music_get(f'http://127.0.0.1:3300/search?key={words}',headers=header)
    r.close()
    if  r is False:
        logger.error('cannot get (request) ,return')
        return
    data = json.loads(r.text)
    logger.info(data)
    for i in range(len(data['data']['list'])):
        if data['data']['list'][i]['pay']['pay_play']==0:
            return [data['data']['list'][i]['songmid'],data['data']['list'][i]['songname'],data['data']['list'][i]['singer'][0]['name']]
    interrupted_music=False
    search=False
    play('Sound/Musicnotfound.wav')
    # music.close()
    return False

def converter(a,b):
    global order
# convert wav to mp3
    try:
        audSeg = AudioSegment.from_file(a)
        audSeg.export(b, format="wav")
        return True
    except Exception as e:
        logger.warning(e)
        play('Sound/convertwrong.wav')
        order=order+1
        return False

def play_search_song(words):
    global musicsound,musicplayer,interrupted_music,search
    back=get_search_song(words)
    if back==False:
        logger.error('wrong in play_search_song ,return ')
        search=False
        return
    r=music_get(f'http://127.0.0.1:3300/song/url?id={back[0]}',headers=header)
    if r is False :
        logger.error('cannot get (request) ,return')
        search=False
        return
    # r.close()
    r=json.loads(r.text)
    if r['result']==100:
        #for i in r['data']:
            #r=requests.get(url=r['data'][i])
        r=music_get(url=r['data'],headers=header)
        if r is False:
            logger.error('cannot get (request) ,return')
            search=False
            return
        with open('Sound/music_search.mp3','wb') as file:
            file.write(r.content)
            file.close()
        r.close()
    else: 
        logger.error('request not 100,return from play_search_song')
        search=False
        return
    converter('Sound/music_search.mp3','Sound/music_search.wav')
    logger.info(f'来自{back[2]}的{back[1]}')
    tts.ssml_save(f'来自{back[2]}的,{back[1]}','Sound/musicnotify.raw')
    play('Sound/ding.wav')
    play('Sound/musicnotify.raw')
    time.sleep(2.5)
    musicsound=arcade.Sound('Sound/music_search.wav',streaming=True)
    musicplayer=musicsound.play(volume=config.get("music_volume"))
    interrupted_music=False
    search=False
    
    logger.info('start play search song')
    music.close()

def play_advice_music(order):
    global musicsound,musicplayer,interrupted_music
    if len(advice)==0:
        logger.error('advice is empty , return from play_adv_music')
        return

    r=music_get(f'http://127.0.0.1:3300/song/urls?id={advice[order]["songmid"]}',headers=header)
    if  r is False :
        logger.error('cannot get (request in play_adv_music) ,return')
        return
    # r.close()
    r=json.loads(r.text)
    if r['result']==100:
        try:

            for i in r['data']:
                r=music_get(url=r['data'][i],headers=header)
            #r=music_get(url=r['data'],headers=header)
            if  r is False or r.status_code>=400:
                interrupted_music = True
                logger.error('cannot get (request in play_adv_music_url) ,return')
                return
        except Exception as e:
            logger.error(f'{e},exit')
            return 
        with open('Sound/music_adv.m4a','wb') as file:
            file.write(r.content)
            file.close()
        r.close()
    else:
        logger.error('respones is not 100 , return from play_adv_music')
        return
    if not converter('Sound/music_adv.m4a','Sound/music_adv.wav'):
        return
    logger.info(f"来自{advice[order]['singer']}的{advice[order]['songname']}")
    tts.ssml_save(f"来自{advice[order]['singer']}的,{advice[order]['songname']}",'Sound/musicnotify.raw')
    play('Sound/ding.wav')
    play('Sound/musicnotify.raw')
    time.sleep(2.5)
    musicsound=arcade.Sound('Sound/music_adv.wav',streaming=True)
    musicplayer=musicsound.play(volume=config.get("music_volume"))
    logger.info('start play advice song')
    music.close()

def stop_music():
    global musicsound,musicplayer
    if musicsound and musicplayer and musicsound.is_playing(musicplayer):
        try:
            
            logger.info('music stopping')
            musicsound.stop(musicplayer)
        except:
            logger.warning('stop sound wrong in if_musci stop func')

def admin_music():
    #if len(advice)==0:
    #    print('advice is empty ,start get list')
    #    get_advice_list()
    while order>=len(advice):
        logger.info('adivce is equal to order ,start get list')
        get_radio_list()
    logger.info(order)
    play_advice_music(order)
    return None

def music_en():
    config.set(MusicPlay=True)


def music_off():
    config.set(MusicPlay=False)

def watch():
    lastime = None
    times=0
    global musicsound,musicplayer,order,interrupted_music,advice,search,startagain,cookiewrong
    while(1):
        if cookiewrong :
            if not startagain:
                continue
        if config.get("MusicPlay"):
            if interrupted_music == True:
                stop_music()
                if search==True:
                    play_search_song(words)
                    times=0
                else:
                    order = order + 1
                    interrupted_music=False
                    # play('Sound/ding.wav')
                    # play(preparefornextmusic.wav')
                    times=0
                    logger.info('Prepare for next music')
                    # 正在为您准备下一首音乐
                    admin_music()
            elif musicsound and musicplayer :
                if musicsound.is_complete(musicplayer):
                    stop_music()
                    order=order+1
                    times=0
                    logger.info('Music service  : next music')
                    admin_music()
                    logger.info('music is playing')
                elif musicsound.is_playing(musicplayer)==False:
                    musicplayer=musicsound.play(volume=config.get("music_volume"))
                times=times+1
                if times>800:
                    interrupted_music=True
                    logger.warning('music stop by time in if_musci')
                    times=0
            elif musicplayer == None:
                admin_music()
                order=order+1
                logger.info('Music service : start play')
        else:
            stop_music()
        if musicsound and musicplayer and musicsound.is_playing(musicplayer):
            if (config.get("chat_enable") or config.get("notify_enable") or config.get("rec_enable")):
                if musicsound.get_volume(musicplayer)!=0.05:
                    musicsound.set_volume(0.05, musicplayer)
                    logger.info('Music service : turn down the volume')
            elif musicsound.get_volume(musicplayer)!=config.get("music_volume"):
                musicsound.set_volume(config.get("music_volume"), musicplayer)
                logger.info('Music service : change the volume')
        if time.localtime()[2]!=lastime:
            lastime=time.localtime()[2]
            advice=[]
            order=0
        time.sleep(0.5)

if __name__=="__main__":
    order=0
    admin_music()
    time.sleep(200)
