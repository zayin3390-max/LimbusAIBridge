"""Reviewed terminology and speaker guidance. Game dialogue stays in the user's local pack."""
from dataclasses import dataclass
import re

@dataclass(frozen=True)
class Term:
    aliases: tuple[str, ...]
    zh: str
    scope: str
    evidence: str
    avoid: tuple[str, ...] = ()

# Each row is a concept, not an unrestricted global string replacement.
# The source identifiers make the preferred wording auditable in a local human pack.
_DATA = """
Coin|Coins;硬币;combat;AbEventsResultLog_Refraction4.json;铜钱
Coin Power;硬币威力;combat;BattleKeywords-a1c7p1.json;铜钱威力
Base Power;基础威力;combat;BattleKeywords-a1c7p1.json;
Unbreakable Coin|Unbreakable Coins;不可摧毁的硬币;combat;AbEventsResultLog_Refraction6.json;不可摧毁的铜钱
Clash|Clashes;拼点;combat;AbEventsResultLog-pilgrimage.json;
Clash Power;拼点威力;combat;ActionEvents-a1c7p3.json;
Attack Weight;攻击容量;combat;TooltipUIText.json;攻击重量
Offense Level;攻击等级;combat;AbEventsResultLog-a1c7p3.json;
Defense Level;防御等级;combat;AbEventsResultLog-a1c7p3.json;
Unopposed Attack|Unopposed Attacks;单方面攻击;combat;BattleKeywords-a1c5p3.json;
Heads;正面;combat;BattleKeywords-a1c9p3.json;
Tails;反面;combat;BattleKeywords-a1c5p2.json;
Potency;强度;combat;AbEventsResultLog_Refraction4.json;
Count;层数;combat;AbEventsResultLog_Refraction3.json;
Sanity|SP;理智值;combat;AbEventsResultLog-a1c5p3.json;
HP;体力;combat;AbEventsResultLog-a1c5p3.json;
Speed;速度值;combat;AbEventsResultLog_Refraction4.json;
Slash;斩击;combat;AbEvents_Mirror4.json;
Pierce;突刺;combat;AbEventsResultLog_Refraction5.json;
Blunt;打击;combat;AbEvents_Mirror4.json;
Resonance;共鸣;combat;BattleHint.json;
Absolute Resonance;完全共鸣;combat;BattleHint.json;
Wrath;暴怒;combat;AbEventsResultLog_Refraction6.json;
Lust;色欲;combat;ActionEvents-a1c7p3.json;
Sloth;怠惰;combat;ActionEvents-cultivation.json;
Gluttony;暴食;combat;AbnormalityGuides.json;贪食
Gloom;忧郁;combat;AbEvents.json;
Pride;傲慢;combat;AbnormalityGuides-a1c7p3.json;
Envy;嫉妒;combat;AbEvents-a1c6p3.json;
Burn;烧伤;combat;AbEvents_Mirror.json;
Bleed;流血;combat;AbEventsResultLog_Refraction6.json;
Tremor;震颤;combat;AbEventsResultLog-a1c6p2.json;
Rupture;破裂;combat;ActionEvents.json;
Sinking;沉沦;combat;AbnormalityGuides.json;
Poise;呼吸法;combat;AbEventsResultLog-a1c971.json;
Charge;充能;combat;AbnormalityGuides-a1c9p2.json;
Haste;迅捷;combat;BattleKeywords-a1c7p1.json;
Bind;束缚;combat;AbEvents_Mirror3.json;
Fragile;易损;combat;BattleKeywords-a1c5p2.json;
Protection;守护;combat;ActionEvents_Refraction5.json;
Paralyze;麻痹;combat;BattleKeywords-BossRaid.json;
Fanatic;狂信;combat;ActionEvents.json;
Attack Power Up;强壮;combat;BattleKeywords-a1c5p1.json;
Damage Up;伤害强化;combat;ActionEvents_Refraction4.json;
Damage Down;伤害弱化;combat;BattleKeywords-a1c6p3.json;
Golden Bough|Golden Boughs;金枝;proper;AbEvents-a1c6p3.json;黄金枝
Lobotomy Corporation;脑叶公司;proper;AbnormalityGuides-walpu6.json;
Limbus Company;边狱公司;proper;ActionEvents-pilgrimage.json;
Abnormality|Abnormalities;异想体;proper;AbEvents-a1c5p3.json;
Bloodfiend|Bloodfiends;血魔;proper;AbEvents_Mirror6.json;
Fixer|Fixers;收尾人;proper;ActionEvents-cultivation.json;
Syndicate|Syndicates;帮派;proper;AbEvents_exme.json;
Backstreets;后巷;proper;AbEvents-pilgrimage.json;
The City;都市;proper;AbEvents_Mirror4.json;
Distortion;扭曲;proper;AbnormalityGuides-a1c6p3.json;
Mirror Dungeon|Mirror Dungeons;镜像迷宫;proper;AbnormalityGuides-a1c7p3.json;
E.G.O Gift|E.G.O Gifts;E.G.O饰品;proper;AbEventsResultLog.json;
Enkephalin;脑啡肽;proper;AbEvents-walpu4.json;
Lunacy;狂气;proper;BattlePass.json;
Identity|Identities;人格;system;AbEvents-a1c5p3.json;
Thread;纺锤;system;BattlePass_Mission.json;
Uptie;同步;system;BattleKeywords.json;
Threadspin;解析;system;BossRaidUI.json;
Sinner|Sinners;罪人;proper;AbEvents-a1c5p3.json;
Yi Sang;李箱;proper;AbDlg_YiSang.json;异乡
Faust;浮士德;proper;AbDlg_Faust.json;
Don Quixote;堂吉诃德;proper;AbDlg_DonQuixote.json;
Ryōshū|Ryoshu|Ryōshu;良秀;proper;AbDlg_Ryoshu.json;
Meursault;默尔索;proper;AbDlg_Merusault.json;
Hong Lu;鸿璐;proper;AbDlg_HongLu.json;
Heathcliff;希斯克利夫;proper;AbDlg_Heathcliff.json;
Ishmael;以实玛利;proper;AbDlg_Ishmael.json;
Rodion|Rodya;罗佳;proper;AbDlg_Rodion.json;
Sinclair;辛克莱;proper;AbDlg_Sinclair.json;
Outis;奥提斯;proper;AbDlg_Outis.json;
Gregor;格里高尔;proper;AbDlg_Gregor.json;
Dante;但丁;proper;AbnormalityGuides-a1c7p3.json;
Vergilius;维吉里乌斯;proper;AbnormalityGuides.json;
Charon;卡戎;proper;Announcer-m4d1.json;
Mephistopheles;梅菲斯托费勒斯;proper;ActionEvents_night-clean-up.json;
"""
TERMS = tuple(Term(tuple(a.split('|')), z, scope, evidence, tuple(filter(None, avoid.split('|'))))
              for a, z, scope, evidence, avoid in
              (line.split(';') for line in _DATA.strip().splitlines()))

# Guidance is our editorial summary of the paired local dialogue, not canonical dialogue.
PROFILES = {
'yi_sang': ('李箱', ('이상','Yi Sang','Yisang','李箱'), '语气克制、沉静，措辞略有文学性。仅在原文有意象、双关或旧式措辞时保留；普通说明不强行文言化。'),
'faust': ('浮士德', ('파우스트','Faust','浮士德'), '冷静、分析式陈述，判断清晰。原文以“浮士德”自称时沿用；不能把所有第一人称都替换为名字，也不能擅自增强确定性。'),
'don_quixote': ('堂吉诃德', ('돈키호테','Don Quixote','DonQuixote','堂吉诃德'), '通常热情、郑重，带骑士式措辞；按当段原文保留对经理的称呼。严肃场景、不同人格与剧情阶段以当前对白为准，不强行套古风或兴奋语气。'),
'ryoshu': ('良秀', ('료슈','Ryōshū','Ryoshu','Ryōshu','良秀'), '简短、冷峭，艺术式比喻和讥讽以原文为限。缩写优先沿用本地汉化对应的间隔号短语；没有释义证据时保留缩写待核对，不编造全称，不在译文中添加解释。'),
'meursault': ('默尔索', ('뫼르소','Meursault','默尔索'), '客观、精确、直接，按观察与指令陈述。保留完整事实、因果和判断，不添加热情、讥讽或机械人口癖。'),
'hong_lu': ('鸿璐', ('홍루','Hong Lu','HongLu','鸿璐'), '温和、从容，好奇时自然发问。保留原有礼貌和亲疏称谓；不把所有疑问写成装傻，不额外加入富家子弟腔。'),
'heathcliff': ('希斯克利夫', ('히스클리프','Heathcliff','希斯克利夫'), '直率、口语化，愤怒和粗话的力度跟随原文；不凭角色印象添加脏话。认真、犹豫或温柔的场景也须照实保留。'),
'ishmael': ('以实玛利', ('이스마엘','Ishmael','以实玛利'), '务实、条理清楚，质疑通常有具体理由。航海措辞仅在原文有关联时使用，不把普通话语都改写成海员俚语。'),
'rodion': ('罗佳', ('로쟈','Rodion','Rodya','罗佳'), '自然亲近，常用轻松口吻、打趣和安慰。保留当段认真或沉重的变化，不擅自添加调情、昵称或亲密关系。'),
'sinclair': ('辛克莱', ('싱클레어','Sinclair','辛克莱'), '通常谨慎、柔和，犹豫按原文保留；坚定场景不强加结巴。仅在原文确实解释良秀缩写时承担解释作用，不凭空补写。'),
'outis': ('奥提斯', ('오티스','Outis','奥提斯'), '正式、军事化且重视判断和执行；对经理的敬称按原文，对其他人的严厉也以原文为限。不要额外增加奉承。'),
'gregor': ('格里高尔', ('그레고르','Gregor','格里高尔'), '口语自然，常有疲惫、自嘲和缓和气氛的意味。不要过分文学化，也不为每一句添加战争往事或叹气。'),
'dante': ('但丁', ('단테','Dante','但丁'), '观察与内心反应较自然，迷惘、关切或坚定以当段为准。保留原有尖括号对白边界；没有说话人证据的旁白不能自动归为但丁。'),
'vergilius': ('维吉里乌斯', ('베르길리우스','Vergilius','维吉里乌斯'), '冷静、简洁、有距离感，威慑通常克制。保留实际语气变化，不添加戏剧化威胁、长篇讽刺或无根据的训斥。'),
'charon': ('卡戎', ('카론','Charon','卡戎'), '短句、具体、直接，按原文保留以名字自称和拟声词。不要自行加入幼儿腔、叠词或解释。')
}

SENSE_NOTES = {
    'Coin / Coins': '战斗掷币、硬币威力：硬币；特定饰品或章节货币的“铜钱”须保留其条目自己的译名。',
    'Wings / Wing': '都市企业语境按本地译文使用“世界之翼／翼”；生物部位是“翅膀／翼”。不得跨语境套用。',
    'Thread': '游戏养成资源是“纺锤”；缝纫线、线索等普通叙事另按上下文翻译。',
    'Identity / Identities': '人格系统使用“人格”；普通身份、身份认同不可机械替换。',
    'Corrosion': 'E.G.O侵蚀、侵蚀技能和普通腐蚀须结合字段，不统一成同一个界面名称。',
    'Hana / Zwei / Tres / Shi / Cinq / Liu / Seven / Eight / Dieci / Öufi / Devyat\'': '协会数字专名保留原拼写，只翻译方位、协会及职务；普通数量按语境翻译。'
}
RESERVED = {a.casefold() for t in TERMS for a in t.aliases} | {
    'wing','wings','corrosion','defense power up','offense level up','defense level up'
}
LABEL_FIELDS = {'name','title','abName','nickName','nameWithTitle','teller','speaker','displayName','place'}
COMBAT_FILE = re.compile(r'^(skills?|passiv|battlekeyword|bufs?|battleui|tooltipui|skilltag|tutorial(?:battle|renewal)|abnormalityguide|enemies)', re.I)
COMBAT_CLUE = re.compile(r'\b(?:Coin Power|Base Power|Unbreakable Coins?|Clash Power|Attack Weight|Offense Level|Defense Level|On (?:Heads |Tails )?Hit)\b', re.I)
MONEY = re.compile(r'\b(?:copper|gold|silver) coins?\b|\bcoins? (?:to (?:buy|purchase)|in (?:my|his|her|the) (?:pocket|wallet))\b', re.I)

def reserved(source):
    return source.casefold() in RESERVED

def narrative(entry):
    file = entry.file.casefold()
    return (file.startswith(('storydata/','personalityvoicedlg/','egovoicedig/','egovoicedlg/','rpgsystem/','battleannouncerdlg/'))
            or file.startswith('abdlg')) and entry.field in {'content','dlg','dialog','text'}

def _pattern(alias, case_sensitive=False):
    return re.compile(r'(?<![\w])'+re.escape(alias)+r'(?![\w])', 0 if case_sensitive else re.I)

_MATCHERS = [(t,a,_pattern(a,t.scope=='proper')) for t in TERMS for a in t.aliases]

def applicable(term, entry):
    name = entry.file.rsplit('/',1)[-1]
    is_label = entry.field in LABEL_FIELDS
    if term.scope == 'proper':
        return True
    if term.scope == 'combat':
        if entry.field in ('flavor','observation','story','dlg','dialog','text') or narrative(entry):
            return bool(COMBAT_CLUE.search(entry.source)) and not MONEY.search(entry.source)
        # A skill or gift title is a named entity, not a dictionary definition.
        if is_label:
            return name.lower().startswith(('bufs','battlekeywords')) and entry.source in term.aliases
        if MONEY.search(entry.source):
            return False
        return bool(COMBAT_FILE.search(name) or COMBAT_CLUE.search(entry.source))
    if term.scope == 'system':
        return (not narrative(entry) and not name.lower().startswith(('skills','passive','ego','enemies'))
                and (entry.source in term.aliases or name.lower().startswith(('items','mainui','rewarddungeon','tutorial','personality','gacha','storytheaterui'))))
    return False

def selected_terms(entry):
    from .core import TOKENS
    plain = TOKENS.sub(lambda m:'\0'*len(m.group()),entry.source)
    selected = []
    for term,alias,pattern in _MATCHERS:
        if not applicable(term,entry):
            continue
        for match in pattern.finditer(plain):
            selected.append((match.start(),match.end(),match.group(),term))
    # A specific multiword concept shields component terms (e.g. Coin Power).
    result = []; covered = []
    for start,end,spelling,term in sorted(selected,key=lambda r:(-(r[1]-r[0]),r[0])):
        if any(a < end and start < b for a,b in covered):
            continue
        result.append((spelling,term));covered.append((start,end))
    return result

def term_locks(entry):
    return {source:term.zh for source,term in selected_terms(entry)}

def repair_known_aliases(entry, text, overrides=None):
    from .core import TOKENS,validate_translation,BridgeError
    original = text
    # Replacement is permitted only for an explicitly reviewed wrong wording,
    # in the matching English concept and sense. Preserve engine token spans.
    replacements = {}
    for source,term in selected_terms(entry):
        if overrides and overrides.get(source,term.zh)!=term.zh:
            continue
        for wrong in term.avoid:
            replacements[wrong] = term.zh
    if not replacements:
        return text
    pattern = re.compile('|'.join(map(re.escape,sorted(replacements,key=len,reverse=True))))
    spans=[];at=0
    for token in TOKENS.finditer(text):
        spans.append(pattern.sub(lambda m:replacements[m.group()],text[at:token.start()]))
        spans.append(token.group());at=token.end()
    spans.append(pattern.sub(lambda m:replacements[m.group()],text[at:]))
    text=''.join(spans)
    try:
        validate_translation(entry.source,text)
    except BridgeError:
        return original
    return text

def terminology_issues(entry, text):
    from .core import TOKENS
    plain = TOKENS.sub('',text)
    return [f'{source} 应使用“{term.zh}”'
            for source,term in selected_terms(entry) if term.zh not in plain]
