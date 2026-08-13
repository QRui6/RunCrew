# 恢复风险安全边界

## 权威运动安全红旗

RunCrew 将以下用户明确报告的运动相关症状视为停止自动训练建议并寻求专业帮助的红旗：

- 胸部疼痛、压迫或明显不适；
- 晕厥、接近晕厥或明显头晕；
- 异常或严重呼吸困难；
- 新出现的明显心律不规则。

依据：

- American Heart Association, “Develop a Physical Activity Plan for You”: https://www.heart.org/en/health-topics/cardiac-rehab/getting-physically-active/develop-a-physical-activity-plan-for-you
- Newcastle Hospitals NHS Foundation Trust, “Exercise and your health: A guide to getting started”: https://www.newcastle-hospitals.nhs.uk/services/newcastle-occupational-health-service/information-for-staff/physiotherapy/self-help-leaflets/exercise-and-your-health-a-guide-to-getting-started/
- NHS, “Chest pain”: https://www.nhs.uk/symptoms/chest-pain/

这些来源支持“停止运动并寻求医疗建议/帮助”的边界，不支持 RunCrew 诊断具体疾病。

## RunCrew 保守工程规则

以下阈值只用于项目的训练编排与回归评测，不是医学指南：

- 疼痛严重度达到8/10：停止自动训练处方并建议专业评估；
- 疼痛达到5/10、发热/急性不适或突发疼痛肿胀发红：建议休息；
- 疲劳5/5，或疲劳至少4/5且睡眠质量不高于2/5：建议休息；
- 疼痛至少3/10、酸痛至少6/10、疲劳至少4/5、睡眠不高于2/5、准备度不高于2/5，或七天训练量增幅超过30%：至少降低训练；
- 规范化训练负荷覆盖率不足80%时，不使用负荷字段计算增幅，改用训练时长代理；
- 最近身体反馈早于评估日前一天时，除红旗升级外返回数据不足。

任何阈值变化都必须升级 `ruleset_version`、更新测试和重新评测，不能在 Prompt 中临时调整。
