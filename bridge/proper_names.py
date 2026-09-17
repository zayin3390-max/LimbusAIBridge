"""Preserve in-world Association number names in the source spelling.

Seven/Eight can also be ordinary numerals: require Association context or an
exact capitalized label. Latin word boundaries permit adjacent Chinese text.
"""
import collections
import re

LATIN = 'A-Za-zÀ-ÖØ-öø-ÿ'
UNAMBIGUOUS = r"Hana|Zwei|Tres|Shi|Cinq|Liu|Dieci|Öufi|Oufi|Devyat[\x27’]?|Devjat[\x27’]?"
CONTEXTUAL = r'(?:Seven|Eight)(?=\s*(?:Assoc(?:iation)?\.?\b|协会|協会))'
STANDALONE = r'(?-i:Seven|Eight)(?=\s*$)'
NAME_PATTERN = (rf'(?<![{LATIN}])(?:{UNAMBIGUOUS}|{CONTEXTUAL})(?![{LATIN}])'
                rf'|\A{STANDALONE}'
                r'|(?<![가-힣])하나(?=\s*(?:협회|协会|協会))')
ASSOCIATION_NAMES = re.compile(NAME_PATTERN,re.I)

def names(text):
    return [match.group() for match in ASSOCIATION_NAMES.finditer(text)]

def strip_names(text):
    return ASSOCIATION_NAMES.sub('',text)

def names_preserved(source,text):
    for spelling,count in collections.Counter(names(source)).items():
        pattern=rf'(?<![{LATIN}]){re.escape(spelling)}(?![{LATIN}])'
        if len(re.findall(pattern,text))!=count:
            return False
    return True
