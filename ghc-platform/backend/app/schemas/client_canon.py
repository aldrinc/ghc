from typing import List, Optional
from pydantic import BaseModel, AnyUrl


class CanonVisualStyleRefs(BaseModel):
    logoUrl: Optional[AnyUrl] = None
    palette: Optional[List[str]] = None
    docUrls: List[AnyUrl] = []


class CanonToneExamples(BaseModel):
    good: List[str] = []
    bad: List[str] = []


class CanonToneOfVoice(BaseModel):
    do: List[str]
    dont: List[str]
    examples: CanonToneExamples = CanonToneExamples()


class CanonBrand(BaseModel):
    story: str
    manifesto: Optional[str] = None
    values: List[str]
    mission: Optional[str] = None
    toneOfVoice: CanonToneOfVoice
    visualStyleRefs: CanonVisualStyleRefs = CanonVisualStyleRefs()


class CanonOffer(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    businessModel: Optional[str] = None
    guarantee: Optional[str] = None
    differentiation: List[str] = []


class CanonICP(BaseModel):
    id: str
    name: str
    pains: List[str] = []
    gains: List[str] = []
    jobsToBeDone: List[str] = []
    segments: List[str] = []


class CanonVoiceOfCustomer(BaseModel):
    quotes: List[str] = []
    objections: List[str] = []
    triggers: List[str] = []
    languagePatterns: List[str] = []


class CanonConstraints(BaseModel):
    legal: List[str] = []
    compliance: List[str] = []
    bannedTopics: List[str] = []
    bannedPhrases: List[str] = []


class CanonContentPatterns(BaseModel):
    goodAssetIds: List[str] = []
    badAssetIds: List[str] = []
    angles: List[str] = []
    hooks: List[str] = []
    formats: List[str] = []


class ClientCanon(BaseModel):
    clientId: str
    brand: CanonBrand
    offers: List[CanonOffer] = []
    icps: List[CanonICP] = []
    voiceOfCustomer: CanonVoiceOfCustomer = CanonVoiceOfCustomer()
    constraints: CanonConstraints = CanonConstraints()
    contentPatterns: CanonContentPatterns = CanonContentPatterns()
