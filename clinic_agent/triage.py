"""Deterministic safety screening and department routing.

The functions in this module intentionally avoid giving a diagnosis. They
identify warning signs that require escalation and suggest where non-urgent
care can be sought.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Iterable, Sequence


class Urgency(str, Enum):
    EMERGENCY = "emergency"
    URGENT = "urgent"
    ROUTINE = "routine"
    SELF_CARE = "self_care"
    INFO_NEEDED = "info_needed"


URGENCY_LABELS = {
    Urgency.EMERGENCY: "疑似急症，请立即就医",
    Urgency.URGENT: "建议24小时内就医",
    Urgency.ROUTINE: "建议择期门诊评估",
    Urgency.SELF_CARE: "可先居家观察，必要时就诊",
    Urgency.INFO_NEEDED: "需要补充更多信息",
}

URGENCY_RANK = {
    Urgency.INFO_NEEDED: 0,
    Urgency.SELF_CARE: 1,
    Urgency.ROUTINE: 2,
    Urgency.URGENT: 3,
    Urgency.EMERGENCY: 4,
}


@dataclass(frozen=True)
class TriageResult:
    urgency: Urgency
    departments: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    follow_ups: list[str] = field(default_factory=list)
    care_advice: list[str] = field(default_factory=list)
    red_flags: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "urgency": self.urgency.value,
            "urgency_label": URGENCY_LABELS[self.urgency],
            "departments": self.departments,
            "reasons": self.reasons,
            "follow_ups": self.follow_ups,
            "care_advice": self.care_advice,
            "red_flags": self.red_flags,
        }


# Each pattern is written as a broad phrase rather than a diagnosis. The action
# message explains why immediate care is needed.
RED_FLAGS: tuple[tuple[str, str], ...] = (
    ("胸痛|心口痛|胸闷伴出冷汗|压榨性胸痛", "胸部疼痛或压迫感可能提示心肺急症"),
    ("呼吸困难|喘不上气|气促明显|嘴唇发紫", "明显呼吸受限或缺氧表现"),
    ("意识不清|昏迷|叫不醒|晕厥|意识模糊", "意识异常需要立即评估"),
    ("抽搐|惊厥|癫痫发作", "抽搐需要紧急处理"),
    ("一侧无力|偏瘫|口角歪斜|说话不清|肢体麻木伴眩晕", "可能提示神经系统急症"),
    ("剧烈头痛|爆炸样头痛|突发最剧烈头痛", "突发剧烈头痛需要排除危急病因"),
    ("大出血|止血困难|喷血|大量呕血|黑便伴乏力", "出血可能快速恶化"),
    ("高热不退|发热超过三天|体温持续升高", "持续高热需要医疗评估"),
    ("严重过敏|全身皮疹伴呼吸困难|喉咙发紧", "严重过敏反应可能迅速加重"),
    ("自杀|不想活|自伤|结束生命", "自杀或自伤风险需要立即获得帮助"),
    ("严重外伤|骨折外露|头部撞击后呕吐", "严重外伤或头部损伤风险"),
    ("剧烈腹痛|腹部剧痛|腹痛拒按", "剧烈腹痛需要排除急腹症"),
    ("孕期出血|孕.*出血|宫外孕", "孕期出血需要紧急产科评估"),
    ("药物过量|误食.*电池|误服.*药物", "急性中毒或误服风险"),
)


DEPARTMENT_RULES: tuple[tuple[str, str, str], ...] = (
    ("儿童|小儿|宝宝|婴儿|.*岁.*(咳嗽|发热|腹泻)", "儿科", "症状涉及儿童"),
    ("孕|月经|阴道|子宫|卵巢|产后|妇科", "妇产科", "症状涉及孕产或妇科系统"),
    ("胸痛|咳嗽|气短|喉咙痛|痰|哮喘", "呼吸内科", "症状涉及呼吸道或胸部"),
    ("心悸|胸闷|高血压|心口", "心血管内科", "症状涉及循环系统"),
    ("腹痛|腹泻|恶心|呕吐|反酸|胃痛|便血|黄疸", "消化内科", "症状涉及消化系统"),
    ("尿频|尿急|尿痛|血尿|肾区痛|排尿困难", "泌尿外科", "症状涉及泌尿系统"),
    ("皮疹|瘙痒|荨麻疹|脱屑|水痘", "皮肤科", "症状涉及皮肤"),
    ("头痛|头晕|失眠|肢体麻木|记忆力下降", "神经内科", "症状涉及神经系统"),
    ("焦虑|抑郁|情绪低落|烦躁|惊恐", "精神心理科", "症状涉及情绪或心理状态"),
    ("关节痛|腰痛|肌肉痛|扭伤|骨折|颈椎|肩痛", "骨科", "症状涉及骨骼肌肉系统"),
    ("牙痛|牙龈|口腔溃疡|智齿", "口腔科", "症状涉及口腔"),
    ("眼睛|视力|眼红|眼痛|畏光", "眼科", "症状涉及眼部"),
    ("耳朵|听力|耳鸣|鼻塞|流鼻涕|咽喉", "耳鼻喉科", "症状涉及耳鼻咽喉"),
    ("发热|乏力|体重下降|体检咨询", "全科医学科", "症状范围较广或暂不明确"),
)

URGENT_RULES: tuple[tuple[str, str], ...] = (
    ("发热超过三天|症状持续超过一周|逐渐加重", "症状持续时间较长或正在加重"),
    ("呕吐无法进食进水|无法进食|无法喝水", "存在脱水或营养摄入风险"),
    ("疼痛.*([7-9]|10)分|剧烈疼痛", "疼痛程度较高"),
    ("婴幼儿|.*个月.*发热|婴儿.*发热", "婴幼儿症状需要尽早评估"),
    ("慢性病|高血压|糖尿病|心脏病|孕期|免疫抑制", "存在基础情况，不宜长期等待"),
)

SELF_CARE_RULES: tuple[tuple[str, str], ...] = (
    ("轻微咳嗽|轻度咳嗽|偶尔咳嗽", "症状描述较轻"),
    ("鼻塞|流鼻涕|打喷嚏", "常见上呼吸道症状"),
    ("轻微咽痛|喉咙有点痛", "症状描述较轻"),
    ("肌肉酸痛|乏力", "症状描述较轻"),
)


def _matches(text: str, pattern: str) -> bool:
    """Match a rule while ignoring simple local negation such as “没有胸痛”."""
    try:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            prefix = text[max(0, match.start() - 6) : match.start()]
            if re.search(r"(没有|无|不|否认)$", prefix):
                continue
            return True
        return False
    except re.error:
        # Bad user-controlled configuration should not crash safety screening.
        start = text.lower().find(pattern.lower())
        if start < 0:
            return False
        prefix = text[max(0, start - 6) : start]
        return not re.search(r"(没有|无|不|否认)$", prefix)


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _max_urgency(left: Urgency, right: Urgency) -> Urgency:
    return left if URGENCY_RANK[left] >= URGENCY_RANK[right] else right


def extract_age(text: str) -> int | None:
    """Extract a plausible age in years from free text."""
    match = re.search(r"(?:年龄[:：]?\s*)?([1-9][0-9]?)\s*岁", text)
    if match:
        return int(match.group(1))
    month_match = re.search(r"([1-9]|1[0-1])\s*个月", text)
    if month_match:
        months = int(month_match.group(1))
        return max(0, months // 12)
    if re.search(r"婴儿|宝宝|新生儿", text, re.IGNORECASE):
        return 1
    return None


def has_medical_content(text: str) -> bool:
    """Return true when the message is substantial enough for screening."""
    normalized = re.sub(r"[\s，。,.!?？!]+", "", text)
    return len(normalized) >= 6


def triage(text: str, *, age_years: int | None = None, history: Sequence[str] = ()) -> TriageResult:
    """Screen one message, considering brief prior messages for continuity."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if age_years is None:
        age_years = extract_age(text)

    context = "\n".join((*history[-4:], text))
    reasons: list[str] = []
    red_flags: list[str] = []
    departments: list[str] = []
    care_advice: list[str] = []
    follow_ups: list[str] = []

    for pattern, reason in RED_FLAGS:
        if _matches(context, pattern):
            red_flags.append(reason)
            reasons.append(reason)

    for pattern, department, reason in DEPARTMENT_RULES:
        if _matches(context, pattern) and department not in departments:
            departments.append(department)
            reasons.append(reason)

    urgency = Urgency.INFO_NEEDED
    if red_flags:
        urgency = Urgency.EMERGENCY
    elif _matches(context, r"(?:不舒服|难受|疼|痛|发热|咳嗽|腹泻|呕吐|皮疹|瘙痒|头晕|心悸)") or departments:
        urgency = Urgency.ROUTINE
        for pattern, reason in URGENT_RULES:
            if _matches(context, pattern):
                urgency = Urgency.URGENT
                reasons.append(reason)
                break

    if age_years is not None and age_years <= 2:
        if _matches(context, r"发热|咳嗽|腹泻|呕吐|精神差|拒奶") and urgency != Urgency.EMERGENCY:
            urgency = Urgency.URGENT
            reasons.append("2岁及以下幼儿症状建议尽早由儿科评估")
        if "儿科" not in departments:
            departments.insert(0, "儿科")

    if urgency == Urgency.SELF_CARE:
        pass

    if urgency == Urgency.ROUTINE and any(_matches(context, pattern) for pattern, _ in SELF_CARE_RULES):
        if not any(_matches(context, urgent) for urgent, _ in URGENT_RULES):
            urgency = Urgency.SELF_CARE

    if not departments and urgency in (Urgency.ROUTINE, Urgency.SELF_CARE):
        departments.append("全科医学科")

    if urgency == Urgency.EMERGENCY:
        care_advice.extend(
            [
                "立即拨打120或前往最近急诊，不要自行开车前往。",
                "若意识变差、呼吸停止或大出血，请让身边人同步呼叫急救并采取现场急救。",
                "带上正在使用的药物、既往病史卡片或病历。",
            ]
        )
    elif urgency == Urgency.URGENT:
        care_advice.extend(
            [
                "请在24小时内联系门诊、急诊或线上问诊医生。",
                "记录症状开始时间、变化和测量到的体温、血压等数据。",
            ]
        )
    elif urgency == Urgency.ROUTINE:
        care_advice.extend(
            [
                "选择建议科室预约门诊；若症状加重或出现夜间剧烈不适，请提高就医级别。",
                "记录症状持续时间、诱因、缓解因素和伴随症状，就诊时提供给医生。",
            ]
        )
    elif urgency == Urgency.SELF_CARE:
        care_advice.extend(
            [
                "保证休息和适量饮水，观察1-3天。",
                "若持续加重、高热不退、进食饮水困难或出现本项目标记的急症提示，请立即就医。",
            ]
        )
    else:
        follow_ups.extend(
            [
                "哪里不舒服？持续了多久？",
                "症状是持续还是间断？最近有没有加重？",
                "疼痛或不舒服程度用0-10分打分，现在大概几分？",
                "有没有慢性病、过敏史、正在使用的药物或特殊生理状态（如孕期）？",
            ]
        )

    if urgency != Urgency.INFO_NEEDED:
        follow_ups.extend(
            [
                "最近一次体温、血压或其他居家测量值是多少？",
                "是否已经自行用药或采取处理措施？效果如何？",
            ]
        )

    return TriageResult(
        urgency=urgency,
        departments=_unique(departments)[:4],
        reasons=_unique(reasons)[:8],
        follow_ups=follow_ups,
        care_advice=care_advice,
        red_flags=_unique(red_flags),
    )


def compose_reply(result: TriageResult, message: str) -> str:
    """Compose a concise, non-diagnostic Chinese reply."""
    if result.urgency == Urgency.INFO_NEEDED:
        return (
            "我先帮你做安全分诊，但不能替代医生诊断。请补充："
            + "；".join(result.follow_ups)
            + "。"
        )

    lines = [
        f"安全级别：{URGENCY_LABELS[result.urgency]}。",
        f"可能适合的科室：{'、'.join(result.departments)}。",
        "主要依据：" + "；".join(result.reasons[:3]) + "。",
    ]
    if result.urgency == Urgency.EMERGENCY:
        lines.insert(1, "如果你现在正处在危险状态，请立即拨打120。")
    lines.append("建议：" + " ".join(result.care_advice))
    lines.append("请继续补充症状细节，我可以帮你整理就诊描述。")
    return "\n".join(lines)
