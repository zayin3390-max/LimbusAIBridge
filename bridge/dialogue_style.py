"""Select traceable human dialogue locally; never learn from model output."""
import collections
import math
import pathlib
import re
from .lexicon import PROFILES
from .core import TOKENS

# E001X explicitly describes switched bodies (rows 90, 101, 103).
# A portrait model is not a safe speaker identity in this scene.
SCENE_NOTES = {'storydata/e001x.json':
    '本场景存在意识与身体互换；model 可能表示身体外观，不足以判断实际说话人。结合当前原文、韩日参考与相邻对白保留实际口吻，不按外观角色套常态语气。'}

# Search cues and editorial usage notes, not a shipped dialogue corpus.
# Activate only with paired human evidence in the current scan.
# Ordinary sentence patterns are not claimed to be unique catchphrases.
HABITS = {
'yi_sang': [
 ('书面疑问',r'\b(?:have you|are you|could|would|may|what|where|how|why|is it)\b',r'可曾|可还|是否|何|之法','可曾／可还／是否',
  '用于探问或沉思，参考例句的简练书面句法；普通问句也可自然直译，不一律文言化。')],
'faust': [
 ('名字自称',r'\bFaust (?:knows|believes|considers|has|is|will|can|shall|must|does)\b',r'浮士德','浮士德',
  '当此处确为以名字自称时保留“浮士德”；I 仍可译“我”，提及其他浮士德时按实际指代处理。')],
'don_quixote': [
 ('经理称呼',r'\bManager Esquire\b',r'经理老爷','经理老爷',
  '用于骑士口吻中对但丁的 Manager Esquire；普通 manager 或不同人格的职务另按当段处理。'),
 ('骑士式人称',r"\b(?:hath|doth|thou|thee|thy|prithee|nay)\b|[’'][Tt]is\b",r'吾|汝','吾／汝',
  '当段已有旧式措辞时参考“吾／汝”的用法；现代口吻、严肃转变及其他人格不强制沿用。')],
'ryoshu': [
 ('冷笑',r'\b(?:pft|hmph)\b',r'噗|哼','噗／哼',
  '原文确有冷笑或鼻音时才采用；短促收尾，不补写笑声。'),
 ('艺术用语',r'\b(?:art|artist|work of art)\b',r'艺术|佳作|作品','艺术／艺术家',
  '保留原有艺术评价和讥讽的力度；不把普通台词改成艺术宣言。缩写另按完整语境核对。')],
'meursault': [
 ('简短应答',r'^(?:Yes|Understood|Affirmative|Acknowledged)\b',r'^(?:是|明白|了解|好的)','是／明白了',
  '肯定与领命可简短应答，保留后面的条件；这是句式参考，不是每句必带的口癖。'),
 ('执行陈述',r'\b(?:orders?|rules?|instructions?)\b',r'命令|规定|指示','命令／规定',
  '执行、规定和观察直接陈述；保留具体条件与因果，不自行加入服从宣言。')],
'hong_lu': [
 ('但丁称呼',r'\bDante\b',r'但丁阁下','但丁阁下',
  '当前确在礼貌称呼但丁时参考；以相同人格和当段关系为准，提及他人不套用。'),
 ('自然笑声',r'\b(?:ahaha|aha|haha)\b',r'哈哈','啊哈哈／哈哈',
  '原文有笑声时按轻重保留；普通疑问和严肃对白不附加笑声或装天真。')],
'heathcliff': [
 ('直接招呼',r'\b(?:oi|hey)\b',r'喂','喂',
  '招呼或喝止时参考短促口语；温柔、犹豫的当段照实保留。'),
 ('粗话力度',r'\b(?:bloody|bugger|shite|shit|damn|fuck)\b',r'妈的|他妈|混账|该死','妈的／混账／该死',
  '只在原文确有粗话时参考力度，不把轻微抱怨统一升级，也不为每句添加脏话。')],
'ishmael': [
 ('条件与理由',r'\b(?:if|because|however|but|provided|unless|otherwise)\b',r'如果|因为|但是|但|否则|前提','但前提是／如果／否则',
  '把判断的前提、反对的理由说清楚；这是论述句式，不是口癖，普通对白不硬加连接词。')],
'rodion': [
 ('感叹与打趣',r'\b(?:oh my|gosh|aw|aww)\b',r'哎呀|哎哟|哎呦','哎呀',
  '用于原有惊讶、感叹或打趣；亲近感来自自然口语，不额外创造昵称或调情。'),
 ('拖长语气',r'[~～]',r'[~～]','～／~',
  '仅原文有拖长语气时参考停顿和语气词；沉重对白不强加轻快尾音。')],
'sinclair': [
 ('但丁称呼',r'\bDante\b',r'但丁经理','但丁经理',
  '礼貌称呼但丁时参考；保留当段对话对象与关系，不替其他人增加职衔。'),
 ('犹豫与改口',r'\b(?:um+|uhm|uh|erm)\b|\bI[-—]I\b',r'那个|呃|嗯|唔|……','那个／呃／嗯……',
  '按原文的迟疑、停顿和自我修正处理；没有犹豫的坚定表达不强加结巴。')],
'outis': [
 ('经理称呼',r'\bExecutive Manager\b',r'执行经理|经理','执行经理／经理',
  '参考正式敬称；本地译例存在长短两种，优先跟随当前场景，不把普通人称统一加官衔。'),
 ('领命',r'^(?:As you order|Understood|Acknowledged|Yes,? (?:Executive )?Manager)\b',r'遵命|明白|了解','遵命／明白',
  '明确领命时用简洁正式应答；原有赞扬照译，不额外增加奉承。')],
'gregor': [
 ('经理称呼',r'\bManager Bud\b',r'经理兄','经理兄',
  '用于与但丁熟络交谈的 Manager Bud，普通职务 manager 不自动改成此称呼。'),
 ('口语缓冲',r'\b(?:well|anyways|anyway|so|excuse me)\b',r'那什么','那什么',
  '犹豫开口、转题或缓和时可参考；仅为常见口语方式，不给每句添加赘词。')],
'dante': [
 ('内心疑问',r'^<.*[?？].*>$',r'^<.*[?？].*>$','尖括号内的疑问与反应',
  '保留尖括号、疑问和当段关切，不额外制造迷惘；无说话人信息的旁白不默认属于但丁。')],
'vergilius': [
 ('克制问责',r"\b(?:why|excuse|anything to say|don[’']t tell me)\b",r'为何|为什么|借口|辩解|难不成','反问／简短问责',
  '用实际问题承载压力，保留原有强度；这是句式参考，不补写训斥或威胁。')],
'charon': [
 ('名字自称',r"\bCharon (?:wants|feels|told|will|has|is|can)\b|\bCharon['’]s got\b",r'卡戎','卡戎',
  '当此处确为名字自称时保留；换身、模仿等特殊情节以当段实际说话者为准。'),
 ('引擎拟声',r'\bvroom(?:-vroom)?\b',r'布隆','布隆布隆',
  '只在原文有相应引擎拟声时用，不在别的台词末尾补写。')]
}
MATCHERS = {who:[(title,re.compile(en,re.I),re.compile(zh),wording,use)
                 for title,en,zh,wording,use in rules] for who,rules in HABITS.items()}

# Stable ID prefixes locate illustrative pairs in the installed pack.
ANCHORS = {
'yi_sang':('lobby_morning','lobby_night','smalltalk_1','battle_select'),
'faust':('lobby_noon','smalltalk_2','lobby_night','battle_select'),
'don_quixote':('get','lobby_night','lobby_noon','smalltalk_1'),
'ryoshu':('smalltalk_2','battle_endcommand','choice_fail','battle_select'),
'meursault':('formation','battle_endcommand','choice_fail','battle_clear_ex'),
'hong_lu':('battle_select','choice_success','smalltalk_2','battle_defeat'),
'heathcliff':('battle_select','smalltalk_3','choice_fail','battle_defeat'),
'ishmael':('smalltalk_2','smalltalk_4','battle_select','battle_endcommand'),
'rodion':('battle_select','smalltalk_2','battle_endcommand','battle_defeat'),
'sinclair':('get','smalltalk_4','battle_endcommand','battle_defeat'),
'outis':('get','battle_endcommand','smalltalk_2','battle_select'),
'gregor':('get','smalltalk_1','battle_endcommand','battle_defeat')
}
STOP = frozenset('a an the i me my you your he she it we they them to of and or is are was were be been am in on at for from this that these those do does did have has had will would can could shall should not with as so but'.split())

def words(text):
    clean=TOKENS.sub(' ',text)
    tokens=[w.casefold() for w in re.findall(r"[A-Za-z]+(?:['’][A-Za-z]+)?",clean)]
    for run in re.findall(r'[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]+',clean):
        tokens.extend(run[i:i+2] for i in range(max(1,len(run)-1)))
    return set(tokens)-STOP

def variant(file):
    file=file.casefold();stem=pathlib.PurePosixPath(file).stem
    if file.startswith('personalityvoicedlg/'):
        if '_lcb_' in stem:return 'base'
        m=re.search(r'_(\d{5,})$',stem)
        return 'identity:'+m[1] if m else 'file:'+file
    if file.startswith(('egovoicedig/','egovoicedlg/')):return 'ego:'+stem
    if file.startswith('rpgsystem/'):return 'story'
    if file.startswith('storydata/'):
        m=re.fullmatch(r'p(\d{5,})[a-z]*',stem)
        return 'identity:'+m[1] if m else 'story'
    return 'file:'+file

def stage(file):
    m=re.match(r'([a-z]*\d)',pathlib.PurePosixPath(file.casefold()).stem)
    return m[1] if m else ''

def public_row(row,relation=None):
    result={k:row[k] for k in ('source','translation','file','path','row_id','variant','model')}
    if relation:result['reference_scope']=relation
    return result

def compatible(current,example):
    if current in ('story','base'):return example in ('story','base')
    return current==example

def anchor_match(row,anchor):
    rid=str(row['row_id'])
    if re.match(r'.*_\d$',anchor):
        stem,number=anchor.rsplit('_',1)
        return rid.startswith(stem+'_') and rid.endswith('_'+number)
    return rid.startswith(anchor+'_')

class DialogueCorpus:
    def __init__(self,examples):
        self.rows=examples
        self.indices=collections.defaultdict(lambda:collections.defaultdict(set))
        for who,rows in self.rows.items():
            for index,row in enumerate(rows):
                row['_words']=words(row['source'])
                row['_habits']=tuple(i for i,(_,en,zh,_,_) in enumerate(MATCHERS.get(who,[]))
                                     if en.search(row['source']) and zh.search(row['translation']))
                for word in row['_words']:self.indices[who][word].add(index)
        self._cache={}

    def _rank(self,who,source,file,row_id=''):
        rows=self.rows.get(who,[]);query=words(source);current=variant(file)
        wanted={i for i,(_,en,_,_,_) in enumerate(MATCHERS.get(who,[])) if en.search(source)}
        scores=[]
        for index,row in enumerate(rows):
            same=row['file'].casefold()==file.casefold()
            fits=compatible(current,row['variant'])
            fallback=not fits and row['variant']=='base'
            if not fits and not fallback:continue
            if same and str(row['row_id'])==str(row_id):continue
            overlap=query & row['_words']
            lexical=sum(math.log(1+len(rows)/(1+len(self.indices[who][w]))) for w in overlap)
            score=lexical+12*len(wanted & set(row['_habits']))
            if same:score+=65
            elif current not in ('story','base') and row['variant']==current:score+=45
            elif row['variant']=='base':score+=7
            elif stage(file) and stage(file)==stage(row['file']):score+=9
            if '?' in source and '?' in row['source']:score+=2
            if '!' in source and '!' in row['source']:score+=1
            score-=abs(math.log((len(source)+20)/(len(row['source'])+20)))
            if fallback:score-=25
            relation=('同文件／场景' if same else '同人格' if current.startswith('identity:') and fits
                      else '同 E.G.O 语音' if current.startswith('ego:') and fits
                      else '基础人格参考，当前人格措辞优先' if fallback
                      else '基础人格语音' if row['variant']=='base' else '其他剧情，阶段可能不同')
            tier=0 if same else 1 if current not in ('story','base') and fits else 3 if fallback else 2
            scores.append((tier,-score,row['file'].casefold(),str(row['row_id']),index,relation))
        return sorted(scores),wanted

    def select(self,who,source,file,row_id='',limit=3,budget=900):
        key=(who,source,file,str(row_id),limit,budget)
        if key in self._cache:return self._cache[key]
        ranked,wanted=self._rank(who,source,file,row_id)
        chosen=[];seen=set();used=0
        for _,_,_,_,index,relation in ranked:
            row=self.rows[who][index];pair=(row['source'],row['translation'])
            cost=len(row['source'])+len(row['translation'])
            if pair in seen or used+cost>budget:continue
            chosen.append(public_row(row,relation));seen.add(pair);used+=cost
            if len(chosen)>=limit:break
        habits=[];current=variant(file)
        for number in sorted(wanted):
            title,_,_,wording,use=MATCHERS[who][number]
            candidates=[self.rows[who][i] for _,_,_,_,i,_ in ranked
                        if number in self.rows[who][i]['_habits']
                        and compatible(current,self.rows[who][i]['variant'])]
            distinct={(r['source'],r['translation']) for r in candidates}
            relevant=next((r for r in chosen if any(r['file']==c['file'] and r['path']==c['path'] for c in candidates)),None)
            if len(distinct)<2 or relevant is None:continue
            habits.append({'type':title,'wording':wording,'when_to_use':use,
                           'evidence':{'file':relevant['file'],'row_id':relevant['row_id']}})
            if len(habits)==2:break
        result={'dialogue_examples':chosen,'speaking_habits':habits}
        self._cache[key]=result
        return result

    def profile(self,who):
        rows=self.rows.get(who,[]);habits=[];chosen=[];seen=set()
        def add(row):
            pair=(row['source'],row['translation'])
            if pair not in seen:chosen.append(public_row(row));seen.add(pair)
        for number,(title,_,_,wording,use) in enumerate(MATCHERS.get(who,[])):
            candidates=[r for r in rows if number in r['_habits'] and r['variant'] in ('base','story')]
            count=len({(r['source'],r['translation']) for r in candidates})
            if count<2:continue
            evidence=sorted(candidates,key=lambda r:(r['variant']!='base',
                not 35<=len(r['source'])<=180,r['file'],str(r['row_id'])))[:2]
            habits.append({'type':title,'wording':wording,'when_to_use':use,'distinct_pairs':count,
                           'files':len({r['file'] for r in candidates}),'examples':[public_row(r) for r in evidence]})
            for r in evidence[:1]:add(r)
        for anchor in ANCHORS.get(who,()):
            row=next((r for r in rows if r['variant']=='base' and anchor_match(r,anchor)),None)
            if row:add(row)
        if len(chosen)<4:
            for r in sorted(rows,key=lambda r:(r['variant'] not in ('base','story'),
                          not 35<=len(r['source'])<=180,r['file'],str(r['row_id']))):
                add(r)
                if len(chosen)>=4:break
        return {'name':PROFILES[who][0],'style':PROFILES[who][2],
                'paired_lines':len(rows),'habits':habits,'examples':chosen[:8]}

    def document(self):
        profiles={who:self.profile(who) for who in PROFILES}
        lines=['# 角色语料与说话方式','',
               '来自当前本地游戏原文与人工汉化的同一字段；不采用 AI 缓存。只保留格式校验通过、原译各不超过 320 字符的完整短句。计数是此子集，不代表全部对白。',
               '已识别的换身剧情 E001X 不纳入常态语料，也不按外观角色套用语气。',
               '每人列出称呼、表达方式及对应原译；常见句式不等于独有口癖。当前台词的情绪、人称、人格和剧情阶段优先，不把例句中的事实搬入新对白。',
               '人格语音优先匹配同一人格编号；缺少同人格语料时仅以基础人格短句辅助句法，并明确标注。新人格不直接继承基础人格的称呼习惯。',
               '每条翻译最多附 3 组原译（正文合计 900 字符）及 2 条有配对依据的表达提示。良秀缩写另附释义候选和相邻对白。','',
               '以下含本地游戏及人工译文，仅供个人核对，不随公开软件分发。','']
        for who,profile in profiles.items():
            lines += [f"## {profile['name']}",'',profile['style'],'',f"可检索短句：{profile['paired_lines']} 组。",'']
            if not profile['habits']:
                lines += ['未检出足够的配对表达证据；用下面的实际句式作参考，不凭印象设定口癖。','']
            for h in profile['habits']:
                lines += [f"### {h['type']}：{h['wording']}",'',h['when_to_use'],
                          f"本地匹配到 {h['distinct_pairs']} 组不同原译，分布于 {h['files']} 个文件。此频次不表示该用词只属于本角色。",'']
                for r in h['examples']:lines += self._format(r)
            lines += ['### 句式与语气对照','']
            for r in profile['examples']:lines += self._format(r)
        return '\n'.join(lines),profiles

    @staticmethod
    def _format(row):
        path='/'.join(map(str,row['path']))
        return [f"- 出处：{row['file']} · ID {row['row_id']} · {path}",
                f"  - 场景类型：{row['variant']}；原模型标识：{row['model'] or '专属语音文件'}",
                '  - 原文：'+row['source'].replace('\n',' / '),
                '  - 人工译文：'+row['translation'].replace('\n',' / '),'']
