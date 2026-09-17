"""Evidence-based filtering of exported localization resources.

The manifest uses basenames for voice resources stored in dedicated folders.
Cross-file coverage requires the same manifest group, stable field identity,
and exact source text; this module never moves or rewrites the human pack.
"""
import pathlib
import re

VOICE_DIRECTORIES = {
    'personalityVoice':'PersonalityVoiceDlg',
    'announcerVoice':'BattleAnnouncerDlg',
    'egoVoice':'EGOVoiceDig',
}

def resource_groups(manifest):
    result={}
    if not isinstance(manifest,dict):
        return result
    for group,resources in manifest.items():
        if not isinstance(resources,list):
            continue
        for resource in resources:
            if not isinstance(resource,str):
                continue
            rel=pathlib.PurePosixPath(resource.replace('\\','/'))
            if rel.suffix.lower() != '.json':
                rel=rel.with_name(rel.name+'.json')
            if len(rel.parts)==1 and group in VOICE_DIRECTORIES:
                rel=pathlib.PurePosixPath(VOICE_DIRECTORIES[group])/rel
            result[str(rel).casefold()]=group
    return result

def canonical_resources(rel,groups):
    name=pathlib.PurePosixPath(rel.casefold()).name
    possible=[name]+[directory.casefold()+'/'+name for directory in VOICE_DIRECTORIES.values()]
    return [p for p in possible if p in groups]

def resource_group(rel,groups):
    key=rel.casefold()
    if key in groups:
        return groups[key]
    # A misplaced duplicate can only match a unique canonical basename.
    matches={groups[p] for p in canonical_resources(rel,groups)}
    return next(iter(matches)) if len(matches)==1 else ''

def engine_note(rel,field,text):
    path=pathlib.PurePosixPath(rel.casefold())
    if field=='desc' and (path.name.startswith('battlespeechbubbledlg')
                         or str(path).startswith('personalityvoicedlg/')):
        return True
    value=text.strip()
    if value in ('UNUSED TEXT','[DEVELOPER COMMENT NOT TO DISPLAY]',
                 '사용 안하는 텍스트','subDesc가 뭘까?','표시용','버프 이름','(더미)'):
        return True
    if value.startswith(('//','SE //')):
        return True
    return '번역x' in value or 'name 만 번역해주세요' in value
