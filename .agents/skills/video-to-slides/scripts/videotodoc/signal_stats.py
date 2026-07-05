"""转录文本的结构形态锚点信号统计（纯计数，不决策 —— Constitution I）。

给整理 agent 一个客观提示：4 个结构形态原型的边界锚点词在全文各命中多少次。
**不输出 ``archetype`` 键**（那会是脚本决策，违反 Constitution I）。类型判定权
始终在 agent（见 SKILL.md 三层证据 L1/L2/L3）。

词表是"提示"非"分类器"——越简单越好，不调大模型。新增锚点词只在此加常量
（Constitution IV 可扩展）。命中计数是柔性参考，agent 自行语义判定。
"""
from __future__ import annotations

import re

# 4 组信号词表，对应 4 原型锚点（见 data-model.md signal_stats 输出形状）。
# _count_group 会按词长降序匹配，避免"第三步"被"第三"重复计数。
_TOPIC_WORDS = (
    "接下来", "说回", "回到", "另外", "话说", "那我们", "好那",
    "刚才", "之前", "之后", "一开始", "最终", "总结一下",
)
_ENUMERATION_WORDS = (
    "第一步", "第二步", "第三步", "第四步", "第五步",
    "第六步", "第七步", "第八步", "第九步", "第十步",
    "第十一步", "第十二步",
    "首先", "接着", "然后", "其次", "再次", "最后",
    "第一", "第二", "第三", "第四", "第五",
    "第六", "第七", "第八", "第九", "第十",
    "第十一", "第十二",
)
_VISUAL_WORDS = (
    "这一页", "下一页", "上一页", "这页", "那页",
    "如图", "看图", "看这张", "这张图", "这张表", "这个图", "这个表",
    "幻灯片", "课件", "PPT", "ppt", "翻到", "翻页",
)
_GRID_WORDS = (
    "第一款", "第二款", "第三款", "第四款",
    "第一个", "第二个", "第三个", "第四个",
    "选手一", "选手二", "选手三", "选手四",
    "续航", "性能", "跑分", "屏幕", "电池", "重量", "外观", "配置", "参数", "像素",
    "对比", "比较", "相比", "优缺点", "区别", "VS", "vs", "PK", "pk",
)

# (原型名, 锚点词表) —— 输出键顺序固定，与 STRATEGY_REGISTRY 4 原型一致。
_GROUPS = (
    ("topic_preserve", _TOPIC_WORDS),
    ("enumeration_unit", _ENUMERATION_WORDS),
    ("visual_event", _VISUAL_WORDS),
    ("rescan_grid", _GRID_WORDS),
)

# 预编译每组正则：词长降序 + re.escape，长词优先匹配避免子串重复计数。
_PATTERNS = {
    name: re.compile("|".join(re.escape(w) for w in sorted(words, key=len, reverse=True)))
    for name, words in _GROUPS
    if words
}


def _count_group(text: str, name: str) -> int:
    """统计 name 组锚点词在 text 中的非重叠命中数。空文本返回 0。"""
    pat = _PATTERNS.get(name)
    if pat is None or not text:
        return 0
    return len(pat.findall(text))


def signal_stats(transcript_text: str) -> dict:
    """统计全文各结构形态原型锚点信号的命中次数。

    返回 ``{原型: 命中计数}``，**不含** ``archetype`` 键（Constitution I：脚本不决策）。
    非字符串输入返回全 0，不抛异常。
    """
    text = transcript_text if isinstance(transcript_text, str) else ""
    return {name: _count_group(text, name) for name, _ in _GROUPS}
