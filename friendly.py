"""Translate failures without inventing a quota or login diagnosis."""
def explain_error(message):
    value=message.lower()
    if '站内消息通道尚未接通' in message:return '还没接通站内消息，请先打开原软件聊天。'
    if any(t in value for t in ('insufficient_quota','quota exceeded','usage limit','额度用尽','usage_limit','quota_exceeded','exceeded your current quota','使用限额','额度已耗尽')):
        return '额度用完，已经休息了。等额度恢复后再来找我。'
    if any(t in value for t in ('context length','context window','token limit reached','上下文过长')):
        return '这段聊天有点长，请缩小问题或新建聊天后继续。'
    if any(t in value for t in ('rate limit','too many requests','429')):
        return '现在有点忙，请稍等一会儿再试。'
    if any(t in value for t in ('unauthorized','not logged','login required','401')):
        return '登录掉线了，请打开原软件重新登录，再回来继续。'
    if any(t in value for t in ('connection','connecterror','network','offline','fetch failed')):
        return '暂时不在线，检查网络和原软件后可以重试。'
    if any(t in value for t in ('timeout','timed out','超时')):
        return '这次想得有点久，还没能完成。可以缩小问题后重试。'
    if '已停止' in message:return '已停止本轮回复。'
    return '这次卡住了，回答尚未完成。可以重试，或检查原软件是否正常。'
