# Slay the Spire 2 敌人知识库（v0.111.0）

本文件由 `scripts/build_enemy_knowledge.py` 从固定版本 Spire Codex 数据生成，并加入少量 SpireMind 战术摘要。
实时意图、能力、生命和卡牌文字始终优先；版本不匹配时运行时不会注入这些资料。

共 115 个条目。来源：[Spire Codex](https://github.com/ptrlrd/spire-codex)。

## 永世沙漏 / Aeonglass (`aeonglass`)

- 类型：boss；区域：Act 3 - Glory
- 特性：Encounter: Act 3 - Glory; HP 512; ascension HP 535. Pattern (cycle): Ebb → Eye Lasers → Increasing Intensity → repeat. Peak listed attack: Ebb 22 (ascension 26). Innate: Artifact 3: Negates debuffs. Utility/special moves: Ebb (Attack + Defend: Ebb 22 (ascension 26), Block 33); Increasing Intensity (Status + Buff: Status + Buff).
- 简略攻略：Strip Artifact before relying on an important Weak, Vulnerable, or other debuff. Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks.

## 建筑师 / The Architect (`architect`)

- 类型：normal；区域：特殊/未知
- 特性：Encounter: special/unknown; HP 9999; ascension HP not listed. Pattern (cycle): Always uses Nothing. Utility/special moves: Nothing (Unknown: Unknown).
- 简略攻略：This is a special encounter entity; follow its live intent and legal actions.

## 劫掠者刺客 / Assassin Raider (`assassin_ruby_raider`)

- 类型：normal；区域：Act 1 - Overgrowth
- 特性：Encounter: Act 1 - Overgrowth; HP 18-23; ascension HP 19-24. Pattern (cycle): Always uses Killshot. Peak listed attack: Killshot 10 (ascension 11).
- 简略攻略：Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 巨斧机器人 / Axebot (`axebot`)

- 类型：normal；区域：Act 3 - Glory
- 特性：Encounter: Act 3 - Glory; HP 70-78; ascension HP 76-86. Pattern (cycle): Always uses Boot Up. Peak listed attack: The One-Two 10x2 (ascension 11x2). Innate: Stock 2: When killed, a new Axebot is summoned in its place. Utility/special moves: Boot Up (Defend + Buff: Block 10, Strength +3 to self); Hammer Uppercut (Attack + Debuff: Hammer Uppercut 14 (ascension 18), Weak +2 to player, Frail +2 to player).
- 简略攻略：Its Stock can replace it after death, so budget damage for the listed replacement count. Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks.

## 劫掠者斧手 / Axe Raider (`axe_ruby_raider`)

- 类型：normal；区域：Act 1 - Overgrowth
- 特性：Encounter: Act 1 - Overgrowth; HP 20-22; ascension HP 21-23. Pattern (cycle): Swing 1 → Swing 2 → Big Swing → repeat. Peak listed attack: Big Swing 12 (ascension 13). Utility/special moves: Swing 1 (Attack + Defend: Swing 1 5 (ascension 6), Block 5); Swing 2 (Attack + Defend: Swing 2 5 (ascension 6), Block 5).
- 简略攻略：Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 战斗好伙伴V1.0 / Battle Friend V1.0 (`battle_friend_v1`)

- 类型：normal；区域：特殊/未知
- 特性：Encounter: special/unknown; HP 75; ascension HP not listed. Innate: Time Limit 3: You have 3 more turns to defeat the Battleworn Dummy. Utility/special moves: Nothing (Unknown: Unknown).
- 简略攻略：Defeat it before the visible Time Limit expires; this encounter is a damage race.

## 战斗好伙伴V2.0 / Battle Friend V2.0 (`battle_friend_v2`)

- 类型：normal；区域：特殊/未知
- 特性：Encounter: special/unknown; HP 150; ascension HP not listed. Innate: Time Limit 3: You have 3 more turns to defeat the Battleworn Dummy. Utility/special moves: Nothing (Unknown: Unknown).
- 简略攻略：Defeat it before the visible Time Limit expires; this encounter is a damage race.

## 战斗好伙伴V3.0 / Battle Friend V3.0 (`battle_friend_v3`)

- 类型：normal；区域：特殊/未知
- 特性：Encounter: special/unknown; HP 300; ascension HP not listed. Innate: Time Limit 3: You have 3 more turns to defeat the Battleworn Dummy. Utility/special moves: Nothing (Unknown: Unknown).
- 简略攻略：Defeat it before the visible Time Limit expires; this encounter is a damage race.

## 盛碗虫（卵） / Bowlbug (Egg) (`bowlbug_egg`)

- 类型：normal；区域：Act 2 - Hive
- 特性：Encounter: Act 2 - Hive; HP 21-22; ascension HP 23-24. Pattern (cycle): Always uses Bite. Peak listed attack: Bite 7 (ascension 8). Utility/special moves: Bite (Attack + Defend: Bite 7 (ascension 8), Block 7).
- 简略攻略：Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 盛碗虫（蜜） / Bowlbug (Nectar) (`bowlbug_nectar`)

- 类型：normal；区域：Act 2 - Hive
- 特性：Encounter: Act 2 - Hive; HP 35-38; ascension HP 36-39. Pattern (cycle): Thrash → Buff → Thrash2 → repeat. Peak listed attack: Thrash 3. Utility/special moves: Buff (Buff: Strength +15 to self).
- 简略攻略：Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 盛碗虫（石） / Bowlbug (Rock) (`bowlbug_rock`)

- 类型：normal；区域：Act 2 - Hive
- 特性：Encounter: Act 2 - Hive; HP 45-48; ascension HP 46-49. Pattern (conditional): Starts with Headbutt. Peak listed attack: Headbutt 15 (ascension 16). Innate: Imbalanced 1: If this creature's attacks are fully blocked, it becomes Stunned. Utility/special moves: Dizzy (Stun: Stun).
- 简略攻略：Re-check the live intent every turn because its pattern is conditional.

## 盛碗虫（丝） / Bowlbug (Silk) (`bowlbug_silk`)

- 类型：normal；区域：Act 2 - Hive
- 特性：Encounter: Act 2 - Hive; HP 40-43; ascension HP 41-44. Peak listed attack: Thrash 4x2 (ascension 5x2). Utility/special moves: Toxic Spit (Debuff: Weak +1 to player).
- 简略攻略：Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks. Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 劫掠者暴徒 / Brute Raider (`brute_ruby_raider`)

- 类型：normal；区域：Act 1 - Overgrowth
- 特性：Encounter: Act 1 - Overgrowth; HP 30-33; ascension HP 31-34. Pattern (cycle): Always uses Beat. Peak listed attack: Beat 7 (ascension 8). Utility/special moves: Roar (Buff: Strength +3 to self).
- 简略攻略：Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 旧日雕像 / Bygone Effigy (`bygone_effigy`)

- 类型：elite；区域：Act 1 - Overgrowth
- 特性：Encounter: Act 1 - Overgrowth; HP 127; ascension HP 132. Pattern (cycle): Sleep → Wake → Slashes → repeat. Peak listed attack: Slashes 13 (ascension 15). Innate: Slow 1: Whenever you play a card, this enemy receives 10% more damage from Attacks this turn. Utility/special moves: Sleep (Sleep: Sleep); Wake (Buff: Strength +10 to self); Sleep Move 2 (Sleep: Sleep).
- 简略攻略：Slow increases the damage this enemy receives for every card played this turn; play weaker attacks first and the strongest multi-hit attack last. After Wake grants Strength, repeated Slashes become a damage race; use Block to cross a survival threshold, not as the default use of all energy.

## 多尼斯异鸟 / Byrdonis (`byrdonis`)

- 类型：elite；区域：Act 1 - Overgrowth
- 特性：Encounter: Act 1 - Overgrowth; HP 81-84; ascension HP 90. Pattern (cycle): Swoop → Peck → repeat. Peak listed attack: Swoop 17 (ascension 19). Innate: Territorial 1: At the end of this creature's turn, it gains  Strength.
- 简略攻略：Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks. Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 异鸟宝宝 / Byrdpip (`byrdpip`)

- 类型：normal；区域：特殊/未知
- 特性：Encounter: special/unknown; HP 9999; ascension HP not listed. Utility/special moves: Nothing (Unknown: Unknown).
- 简略攻略：This is a special encounter entity; follow its live intent and legal actions.

## 钙化邪教徒 / Calcified Cultist (`calcified_cultist`)

- 类型：normal；区域：Act 1 - Underdocks
- 特性：Encounter: Act 1 - Underdocks; HP 38-41; ascension HP 39-42. Pattern (cycle): Always uses Incantation. Peak listed attack: Dark Strike 9 (ascension 11). Utility/special moves: Incantation (Buff: Ritual +2 to self).
- 简略攻略：Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 仪式兽 / Ceremonial Beast (`ceremonial_beast`)

- 类型：boss；区域：Act 1 - Overgrowth
- 特性：Encounter: Act 1 - Overgrowth; HP 252; ascension HP 262. Pattern (cycle): Stamp → Plow → repeat. Peak listed attack: Plow 18 (ascension 20). Utility/special moves: Stamp (Buff: Plow +150 to self); Plow (Attack + Buff: Plow 18 (ascension 20), Strength +2 to self); Stun (Stun: Stun); Beast Cry (Debuff: Ringing +1 to player).
- 简略攻略：Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 啃咬机 / Chomper (`chomper`)

- 类型：normal；区域：Act 2 - Hive
- 特性：Encounter: Act 2 - Hive; HP 60-64; ascension HP 63-67. Peak listed attack: Clamp 8x2 (ascension 9x2). Innate: Artifact 2: Negates debuffs. Utility/special moves: Screech (Status: Status).
- 简略攻略：Strip Artifact before relying on an important Weak, Vulnerable, or other debuff. Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks.

## 噬尸蛞蝓 / Corpse Slug (`corpse_slug`)

- 类型：normal；区域：Act 1 - Underdocks
- 特性：Encounter: Act 1 - Underdocks; HP 25-27; ascension HP 27-29. Peak listed attack: Glomp 8 (ascension 9). Innate: Ravenous 4: When an enemy dies, Corpse Slug immediately eats it, becoming Stunned and gaining 1 Strength. Utility/special moves: Goop (Debuff: Frail +2 to player).
- 简略攻略：Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks. Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 劫掠者弩手 / Crossbow Raider (`crossbow_ruby_raider`)

- 类型：normal；区域：Act 1 - Overgrowth
- 特性：Encounter: Act 1 - Overgrowth; HP 18-21; ascension HP 19-22. Peak listed attack: Fire! 14 (ascension 16). Utility/special moves: Reload (Defend: Block 3).
- 简略攻略：Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 碾碎爪 / Crusher (`crusher`)

- 类型：boss；区域：Act 2 - Hive
- 特性：Encounter: Act 2 - Hive; HP 209; ascension HP 219. Pattern (cycle): Thrash → Enlarging Strike → Bug Sting → Adapt → Guarded Strike → repeat. Peak listed attack: Thrash 12 (ascension 14). Innate: Back Attack 1: Deals 50% more damage when it is attacking you from behind; Crab Rage 1: When an ally dies, this creature gains 6 Strength and 99 Block. Utility/special moves: Bug Sting (Attack + Debuff: Bug Sting 6x2 (ascension 7x2), Weak +2 to player, Frail +2 to player); Adapt (Buff: Strength +2 to self); Guarded Strike (Attack + Defend: Guarded Strike 12 (ascension 14), Block 18).
- 简略攻略：Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks. Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 方柱构装体 / Cubex Construct (`cubex_construct`)

- 类型：normal；区域：Act 1 - Overgrowth, Act 3 - Glory
- 特性：Encounter: Act 1 - Overgrowth, Act 3 - Glory; HP 65; ascension HP 70. Pattern (cycle): Charge Up → Repeater Blast → Repeater Blast Move 2 → Expel → repeat. Peak listed attack: Expel 5x2 (ascension 6x2). Innate: Artifact 1: Negates debuffs. Utility/special moves: Charge Up (Buff: Strength +2 to self); Repeater Blast (Attack + Buff: Repeater Blast 7 (ascension 8), Strength +2 to self); Repeater Blast Move 2 (Attack + Buff: Repeater Blast Move 2 7 (ascension 8), Strength +2 to self).
- 简略攻略：Strip Artifact before relying on an important Weak, Vulnerable, or other debuff. Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks. Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 潮湿邪教徒 / Damp Cultist (`damp_cultist`)

- 类型：normal；区域：Act 1 - Underdocks
- 特性：Encounter: Act 1 - Underdocks; HP 51-53; ascension HP 52-54. Pattern (cycle): Always uses Incantation. Peak listed attack: Dark Strike 1 (ascension 3). Utility/special moves: Incantation (Buff: Ritual +5 to self).
- 简略攻略：Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 残杀千足虫 / Decimillipede (`decimillipede_segment`)

- 类型：elite；区域：特殊/未知
- 特性：Encounter: special/unknown; HP 40-46; ascension HP 46-52. Peak listed attack: Writhe 5x2 (ascension 6x2). Innate: Reattach 25: If other segments are still alive, revives in 2 turns with 25 HP. Utility/special moves: Bulk (Attack + Buff: Bulk 6 (ascension 7), Strength +2 to self); Constrict (Attack + Debuff: Constrict 8 (ascension 9), Weak +1 to player); Dead (Unknown: Unknown); Reattach (Heal: Heal).
- 简略攻略：Save enough burst to outpace or finish through its listed healing turn. Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks.

## Decimillipede Segment (Back) / Decimillipede Segment (Back) (`decimillipede_segment_back`)

- 类型：elite；区域：Act 2 - Hive
- 特性：Encounter: Act 2 - Hive; HP 40-46; ascension HP 46-52. Peak listed attack: Writhe 5x2 (ascension 6x2). Utility/special moves: Bulk (Attack + Buff: Bulk 6 (ascension 7), Strength +2 to self); Constrict (Attack + Debuff: Constrict 8 (ascension 9), Weak +1 to player); Dead (Unknown: Unknown); Reattach (Heal: Heal).
- 简略攻略：Save enough burst to outpace or finish through its listed healing turn. Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks.

## Decimillipede Segment (Front) / Decimillipede Segment (Front) (`decimillipede_segment_front`)

- 类型：elite；区域：Act 2 - Hive
- 特性：Encounter: Act 2 - Hive; HP 40-46; ascension HP 46-52. Peak listed attack: Writhe 5x2 (ascension 6x2). Utility/special moves: Bulk (Attack + Buff: Bulk 6 (ascension 7), Strength +2 to self); Constrict (Attack + Debuff: Constrict 8 (ascension 9), Weak +1 to player); Dead (Unknown: Unknown); Reattach (Heal: Heal).
- 简略攻略：Save enough burst to outpace or finish through its listed healing turn. Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks.

## Decimillipede Segment (Middle) / Decimillipede Segment (Middle) (`decimillipede_segment_middle`)

- 类型：elite；区域：Act 2 - Hive
- 特性：Encounter: Act 2 - Hive; HP 40-46; ascension HP 46-52. Peak listed attack: Writhe 5x2 (ascension 6x2). Utility/special moves: Bulk (Attack + Buff: Bulk 6 (ascension 7), Strength +2 to self); Constrict (Attack + Debuff: Constrict 8 (ascension 9), Weak +1 to player); Dead (Unknown: Unknown); Reattach (Heal: Heal).
- 简略攻略：Save enough burst to outpace or finish through its listed healing turn. Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks.

## 虔诚雕刻师 / Devoted Sculptor (`devoted_sculptor`)

- 类型：normal；区域：Act 3 - Glory
- 特性：Encounter: Act 3 - Glory; HP 162; ascension HP 172. Pattern (cycle): Always uses Forbidden Incantation. Peak listed attack: Savage 12 (ascension 15). Utility/special moves: Forbidden Incantation (Buff: Buff).
- 简略攻略：Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 蜂群术士 / Entomancer (`entomancer`)

- 类型：elite；区域：Act 2 - Hive
- 特性：Encounter: Act 2 - Hive; HP 145; ascension HP 165. Pattern (cycle): Always uses Beeeees!. Peak listed attack: Beeeees! 3x7 (ascension 3x7). Innate: Personal Hive 1: Whenever this enemy is hit by an Attack, add Dazed into your Draw Pile. Utility/special moves: Pheromone Spit (Buff: Strength +2 to self, Personal Hive +1 to self, Strength +1 to self).
- 简略攻略：Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks. Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 外骨骼虫 / Exoskeleton (`exoskeleton`)

- 类型：normal；区域：Act 2 - Hive
- 特性：Encounter: Act 2 - Hive; HP 24-28; ascension HP 26-30. Pattern (mixed): then random: Skitter (no repeat), Mandibles (no repeat); then conditional: Skitter (if in first slot) / Mandibles (if in second slot) / Enrage (if in third slot) / Rand (if in fourth slot). Peak listed attack: Mandibles 8 (ascension 9). Innate: Hard to Kill 9: Reduce all damage taken and HP lost by this creature to. Utility/special moves: Enrage (Buff: Strength +2 to self).
- 简略攻略：Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks. Re-check the live intent every turn because its pattern is mixed.

## 利齿之眼 / Eye with Teeth (`eye_with_teeth`)

- 类型：normal；区域：Act 1 - Overgrowth
- 特性：Encounter: Act 1 - Overgrowth; HP 6; ascension HP not listed. Pattern (cycle): Always uses Distract. Innate: Illusion 1: When this dies, it revives next turn at full HP. Utility/special moves: Distract (Status: Status).
- 简略攻略：Keep draw and mitigation available for status/debuff turns instead of overcommitting setup.

## 组装师 / Fabricator (`fabricator`)

- 类型：normal；区域：Act 3 - Glory
- 特性：Encounter: Act 3 - Glory; HP 150; ascension HP 155. Pattern (mixed): then random: Fabricate, Fabricating Strike; then conditional: Rand (if can fabricate) / Disintegrate (if cannot fabricate). Peak listed attack: Fabricating Strike 18 (ascension 21). Utility/special moves: Fabricate (Summon: Summon).
- 简略攻略：Do not allow summons to multiply pressure; prioritize the summoner or the most dangerous add. Re-check the live intent every turn because its pattern is mixed.

## 商人？？？ / The Merchant??? (`fake_merchant_monster`)

- 类型：normal；区域：特殊/未知
- 特性：Encounter: special/unknown; HP 165; ascension HP 175. Pattern (random): Starts with Swipe. Peak listed attack: Spew Coins 2x8. Utility/special moves: Throw Relic (Attack + Debuff: Throw Relic 9 (ascension 10), Frail +1 to player); Enrage (Buff: Strength +2 to self).
- 简略攻略：Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks. Re-check the live intent every turn because its pattern is random.

## 胖地精 / Fat Gremlin (`fat_gremlin`)

- 类型：normal；区域：Act 1 - Underdocks
- 特性：Encounter: Act 1 - Underdocks; HP 13-17; ascension HP 14-18. Pattern (cycle): Always uses Wake Up. Utility/special moves: Wake Up (Stun: Stun); Flee (Escape: Escape).
- 简略攻略：Front-load damage if allowing its escape would lose rewards or prolong the encounter.

## 连枷骑士 / Flail Knight (`flail_knight`)

- 类型：elite；区域：Act 3 - Glory
- 特性：Encounter: Act 3 - Glory; HP 101; ascension HP 108. Pattern (random): Starts with Ram. Peak listed attack: Flail 9x2 (ascension 10x2). Utility/special moves: War Chant (Buff: Strength +3 to self).
- 简略攻略：Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks. Re-check the live intent every turn because its pattern is random.

## 飞蝇菌子 / Flyconid (`flyconid`)

- 类型：normal；区域：Act 1 - Overgrowth
- 特性：Encounter: Act 1 - Overgrowth; HP 47-49; ascension HP 51-53. Peak listed attack: Smash 11 (ascension 12). Utility/special moves: Vulnerable Spores (Debuff: Vulnerable Spores 8 (ascension 9), Vulnerable +2 to player); Frail Spores (Attack + Debuff: Frail Spores 8 (ascension 9), Frail +2 to player).
- 简略攻略：Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Re-check the live intent every turn because its pattern is random.

## 雾菇 / Fogmog (`fogmog`)

- 类型：normal；区域：Act 1 - Overgrowth
- 特性：Encounter: Act 1 - Overgrowth; HP 74; ascension HP 78. Pattern (random): Starts with Illusory Spores, then random: Swipe Random (no repeat, 40%), Headbutt (no repeat, 60%). Peak listed attack: Headbutt 14 (ascension 16). Utility/special moves: Illusory Spores (Summon: Summon); Thwack (Attack + Buff: Thwack 8 (ascension 9), Strength +1 to self); Swipe Random (Attack + Buff: Swipe Random 8 (ascension 9), Strength +1 to self).
- 简略攻略：Do not allow summons to multiply pressure; prioritize the summoner or the most dangerous add. Re-check the live intent every turn because its pattern is random.

## 化石追踪者 / Fossil Stalker (`fossil_stalker`)

- 类型：normal；区域：Act 1 - Underdocks
- 特性：Encounter: Act 1 - Underdocks; HP 51-53; ascension HP 54-56. Pattern (random): Starts with Latch. Peak listed attack: Latch 12 (ascension 14). Innate: Suck 3: Whenever this creature deals unblocked attack damage, it gains  Strength. Utility/special moves: Tackle (Attack + Debuff: Tackle 9 (ascension 11), Frail +1 to player).
- 简略攻略：Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks. Re-check the live intent every turn because its pattern is random.

## 青蛙骑士 / Frog Knight (`frog_knight`)

- 类型：normal；区域：Act 3 - Glory
- 特性：Encounter: Act 3 - Glory; HP 191; ascension HP 199. Pattern (conditional): Starts: Tongue Lash → Strike Down Evil → For the Queen; then conditional: Tongue Lash (if HasBeetleCharged || CurrentHp >= MaxHp / 2) / Beetle Charge (if !HasBeetleCharged && CurrentHp < MaxHp / 2). Peak listed attack: Beetle Charge 35 (ascension 40). Innate: Plating 15: At the end of your turn, gain  Block. Plating is reduced by 1 at the start of your turn. Utility/special moves: For the Queen (Buff: Strength +5 to self); Tongue Lash (Attack + Debuff: Tongue Lash 13 (ascension 14), Frail +2 to player).
- 简略攻略：Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Plan a dedicated Block, Weak, or lethal turn for Beetle Charge; it is the peak listed hit. Re-check the live intent every turn because its pattern is conditional.

## 毛绒伏地虫 / Fuzzy Wurm Crawler (`fuzzy_wurm_crawler`)

- 类型：normal；区域：Act 1 - Overgrowth
- 特性：Encounter: Act 1 - Overgrowth; HP 55-57; ascension HP 58-59. Pattern (cycle): Always uses First Acid Goop. Peak listed attack: First Acid Goop 4 (ascension 6). Utility/special moves: Inhale (Buff: Strength +7 to self).
- 简略攻略：Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 气态炸弹 / Gas Bomb (`gas_bomb`)

- 类型：normal；区域：Act 1 - Underdocks
- 特性：Encounter: Act 1 - Underdocks; HP 7; ascension HP 8. Pattern (cycle): Always uses Explode. Peak listed attack: Explode 8 (ascension 9). Innate: Minion 1: Minions abandon combat without their leader.
- 简略攻略：Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 电球头 / Globe Head (`globe_head`)

- 类型：normal；区域：Act 3 - Glory
- 特性：Encounter: Act 3 - Glory; HP 148; ascension HP 158. Pattern (cycle): Shocking Slap → Channel Lightning → Galvanic Burst → repeat. Peak listed attack: Channel Lightning 6x3 (ascension 7x3). Innate: Galvanic 6: Powers are afflicted with Galvanized. Utility/special moves: Shocking Slap (Attack + Debuff: Shocking Slap 13 (ascension 14), Frail +2 to player); Galvanic Burst (Attack + Buff: Galvanic Burst 16 (ascension 17), Strength +2 to self).
- 简略攻略：Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks. Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 地精佣兵 / Gremlin Merc (`gremlin_merc`)

- 类型：normal；区域：Act 1 - Underdocks
- 特性：Encounter: Act 1 - Underdocks; HP 47-49; ascension HP 51-53. Pattern (cycle): Gimme → Double Smash → Hehe → repeat. Peak listed attack: Gimme 7x2 (ascension 8x2). Innate: Surprise 1: Something is off about this creature. Utility/special moves: Double Smash (Attack + Debuff: Double Smash 6x2 (ascension 7x2), Weak +2 to player); Hehe (Attack + Buff: Hehe 8 (ascension 9), Strength +2 to self).
- 简略攻略：Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks. Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 守护机器人 / Guardbot (`guardbot`)

- 类型：normal；区域：特殊/未知
- 特性：Encounter: special/unknown; HP 16-20; ascension HP 17-21. Pattern (cycle): Always uses Guard. Utility/special moves: Guard (Defend: Block 15).
- 简略攻略：This is a special encounter entity; follow its live intent and legal actions.

## 幽灵船 / Haunted Ship (`haunted_ship`)

- 类型：normal；区域：Act 1 - Underdocks
- 特性：Encounter: Act 1 - Underdocks; HP 63; ascension HP 67. Pattern (cycle): Haunt → Swipe → Stomp → repeat. Peak listed attack: Stomp 4x3 (ascension 5x3). Utility/special moves: Haunt (Debuff + Status: Weak +3 to player).
- 简略攻略：Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks. Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 猎人杀手 / Hunter Killer (`hunter_killer`)

- 类型：normal；区域：Act 2 - Hive
- 特性：Encounter: Act 2 - Hive; HP 121; ascension HP 126. Pattern (random): Starts with Tenderizing Goop. Peak listed attack: Puncture 7x3 (ascension 8x3). Utility/special moves: Tenderizing Goop (Debuff: Tender +1 to player).
- 简略攻略：Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks. Re-check the live intent every turn because its pattern is random.

## 感染棱柱 / Infested Prism (`infested_prism`)

- 类型：elite；区域：Act 2 - Hive
- 特性：Encounter: Act 2 - Hive; HP 161; ascension HP 171. Pattern (cycle): Jab → Radiate → Whirlwind → Pulsate → repeat. Peak listed attack: Whirlwind 5x3 (ascension 6x3). Innate: Vital Spark 2: ALL Skills are Tainted 2. Utility/special moves: Radiate (Attack + Defend: Radiate 11 (ascension 13), Block 11); Pulsate (Attack + Buff + Defend: Pulsate 8 (ascension 10), Block 20, Vital Spark +2 to self).
- 简略攻略：Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks. Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 墨宝 / Inklet (`inklet`)

- 类型：normal；区域：Act 1 - Overgrowth
- 特性：Encounter: Act 1 - Overgrowth; HP 11-17; ascension HP 12-18. Pattern (random): Starts: Whirlwind → Jab; then random: Jab, Whirlwind (no repeat); then random: Piercing Gaze (no repeat), Whirlwind (no repeat). Peak listed attack: Piercing Gaze 10 (ascension 11). Innate: Slippery 1: The next 2 times this creature loses HP, it only loses 1 HP instead.
- 简略攻略：Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks. Re-check the live intent every turn because its pattern is random.

## 同族信徒 / Kin Follower (`kin_follower`)

- 类型：boss；区域：Act 1 - Overgrowth
- 特性：Encounter: Act 1 - Overgrowth; HP 58-59; ascension HP 62-63. Pattern (cycle): Power Dance → Quick Slash → Boomerang → repeat. Peak listed attack: Quick Slash 5 (ascension 5). Innate: Minion 1: Minions abandon combat without their leader. Utility/special moves: Power Dance (Buff: Strength +2 to self).
- 简略攻略：Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks. Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 同族神官 / Kin Priest (`kin_priest`)

- 类型：boss；区域：Act 1 - Overgrowth
- 特性：Encounter: Act 1 - Overgrowth; HP 190; ascension HP 199. Pattern (cycle): Orb of Frailty → Orb of Weakness → Soul Beam → Dark Ritual → repeat. Peak listed attack: Orb of Frailty 8 (ascension 9). Utility/special moves: Orb of Frailty (Attack + Debuff: Orb of Frailty 8 (ascension 9), Frail +1 to player); Orb of Weakness (Attack + Debuff: Orb of Weakness 8 (ascension 9), Weak +1 to player); Dark Ritual (Buff: Strength +2 to self).
- 简略攻略：Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks. Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 知识恶魔 / Knowledge Demon (`knowledge_demon`)

- 类型：boss；区域：Act 2 - Hive
- 特性：Encounter: Act 2 - Hive; HP 379; ascension HP 399. Pattern (conditional): Starts: Curse of Knowledge → Slap → Knowledge Overwhelming → Ponder; then conditional: Curse of Knowledge (if curse of knowledge counter < 3) / Slap (if curse of knowledge counter >= 3). Peak listed attack: Knowledge Overwhelming 8x3 (ascension 9x3). Utility/special moves: Curse of Knowledge (Debuff: Debuff); Ponder (Attack + Heal + Buff: Ponder 11 (ascension 13), heal 30, Strength +2 to self).
- 简略攻略：Save enough burst to outpace or finish through its listed healing turn. Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks.

## 乐加维林族母 / Lagavulin Matriarch (`lagavulin_matriarch`)

- 类型：boss；区域：Act 1 - Underdocks
- 特性：Encounter: Act 1 - Underdocks; HP 222; ascension HP 233. Pattern (conditional): Starts with Sleep. Peak listed attack: Slash 19 (ascension 21). Innate: Plating 12: At the end of your turn, gain  Block. Plating is reduced by 1 at the start of your turn; Asleep 3: Awakens upon losing HP or after 2 turns. Utility/special moves: Sleep (Sleep: Sleep); Slash2 (Attack + Defend: Slash2 12 (ascension 14), Block 12); Soul Siphon (Debuff + Buff: Strength +2 to self).
- 简略攻略：Use safe sleeping turns to set up, then commit damage when ready for the wake-up pattern. Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks.

## 树叶史莱姆（中） / Leaf Slime (M) (`leaf_slime_m`)

- 类型：normal；区域：Act 1 - Overgrowth
- 特性：Encounter: Act 1 - Overgrowth; HP 32-35; ascension HP 33-36. Pattern (cycle): Sticky Shot → Clump Shot → repeat. Peak listed attack: Clump Shot 8 (ascension 9). Utility/special moves: Sticky Shot (Status: Status).
- 简略攻略：Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 树叶史莱姆（小） / Leaf Slime (S) (`leaf_slime_s`)

- 类型：normal；区域：Act 1 - Overgrowth
- 特性：Encounter: Act 1 - Overgrowth; HP 11-15; ascension HP 12-16. Peak listed attack: Tackle 3 (ascension 4). Utility/special moves: Goop (Status: Status).
- 简略攻略：Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Re-check the live intent every turn because its pattern is random.

## 活雾 / Living Fog (`living_fog`)

- 类型：normal；区域：Act 1 - Underdocks
- 特性：Encounter: Act 1 - Underdocks; HP 80; ascension HP 82. Pattern (cycle): Advanced Gas → Bloat → Super Gas Blast → repeat. Peak listed attack: Advanced Gas 8 (ascension 9). Utility/special moves: Advanced Gas (Attack + Debuff: Advanced Gas 8 (ascension 9), Smoggy +1 to player).
- 简略攻略：Do not allow summons to multiply pressure; prioritize the summoner or the most dangerous add. Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 活体盾 / Living Shield (`living_shield`)

- 类型：normal；区域：Act 3 - Glory
- 特性：Encounter: Act 3 - Glory; HP 55; ascension HP 65. Pattern (conditional): Starts with Shield Slam; then conditional: Shield Slam (if has allies) / Smash (if no allies). Peak listed attack: Smash 16 (ascension 18). Innate: Rampart 25: At the start of the player's turn, Turret Operator gains 25 Block. Utility/special moves: Smash (Attack + Buff: Smash 16 (ascension 18), Strength +3 to self).
- 简略攻略：Re-check the live intent every turn because its pattern is conditional.

## 虱虫之祖 / Louse Progenitor (`louse_progenitor`)

- 类型：normal；区域：Act 2 - Hive
- 特性：Encounter: Act 2 - Hive; HP 134-136; ascension HP 138-141. Pattern (cycle): Always uses Web Cannon. Peak listed attack: Pounce 14 (ascension 16). Innate: Curl Up 14: When damaged, rolls up and gains block. (Once per combat). Utility/special moves: Web Cannon (Attack + Debuff: Web Cannon 9 (ascension 10), Frail +2 to player); Curl and Grow (Defend + Buff: Block 14, Strength +5 to self).
- 简略攻略：Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 魔法骑士 / Magi Knight (`magi_knight`)

- 类型：elite；区域：Act 3 - Glory
- 特性：Encounter: Act 3 - Glory; HP 82; ascension HP 89. Pattern (cycle): Power Shield → Dampen → Ram → Prep → Magic Bomb → repeat. Peak listed attack: Magic Bomb 35 (ascension 40). Utility/special moves: Power Shield (Attack + Defend: Power Shield 6 (ascension 7), Block 5); Dampen (Debuff: Debuff); Prep (Defend: Block 5).
- 简略攻略：Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Plan a dedicated Block, Weak, or lethal turn for Magic Bomb; it is the peak listed hit. Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 蛮兽 / Mawler (`mawler`)

- 类型：normal；区域：Act 1 - Overgrowth
- 特性：Encounter: Act 1 - Overgrowth; HP 72; ascension HP 76. Pattern (random): Starts with Claw; then random: Rip and Tear (no repeat), Roar (once), Claw (no repeat). Peak listed attack: Rip and Tear 14 (ascension 16). Utility/special moves: Roar (Debuff: Vulnerable +3 to player).
- 简略攻略：Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks. Re-check the live intent every turn because its pattern is random.

## 机甲骑士 / Mecha Knight (`mecha_knight`)

- 类型：elite；区域：Act 3 - Glory
- 特性：Encounter: Act 3 - Glory; HP 300; ascension HP 320. Pattern (cycle): Charge → Flamethrower → Windup → Heavy Cleave → repeat. Peak listed attack: Heavy Cleave 35 (ascension 40). Innate: Artifact 3: Negates debuffs. Utility/special moves: Windup (Defend + Buff: Block 15, Strength +5 to self).
- 简略攻略：Strip Artifact before relying on an important Weak, Vulnerable, or other debuff. Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Plan a dedicated Block, Weak, or lethal turn for Heavy Cleave; it is the peak listed hit.

## 神秘骑士 / Mysterious Knight (`mysterious_knight`)

- 类型：normal；区域：特殊/未知
- 特性：Encounter: special/unknown; HP 101; ascension HP 108. Peak listed attack: Flail 9x2 (ascension 10x2). Utility/special moves: War Chant (Buff: Strength +3 to self).
- 简略攻略：Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks.

## 异螨 / Myte (`myte`)

- 类型：normal；区域：Act 2 - Hive
- 特性：Encounter: Act 2 - Hive; HP 61-67; ascension HP 64-69. Pattern (conditional): then conditional: Toxic Cornucopia (if in first slot) / Suck (if in second slot). Peak listed attack: Bite 13 (ascension 15). Utility/special moves: Toxic Cornucopia (Status: Status); Suck (Attack + Buff: Suck 4 (ascension 6), Strength +2 to self).
- 简略攻略：Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Re-check the live intent every turn because its pattern is conditional.

## 小啃兽 / Nibbit (`nibbit`)

- 类型：normal；区域：Act 1 - Overgrowth
- 特性：Encounter: Act 1 - Overgrowth; HP 42-46; ascension HP 44-48. Pattern (conditional): then conditional: Butt (if alone) / Hiss (if not in front) / Slice (if in front). Peak listed attack: Butt 12 (ascension 13). Utility/special moves: Slice (Attack + Defend: Slice 6 (ascension 7), Block 5); Hiss (Buff: Strength +2 to self).
- 简略攻略：Re-check the live intent every turn because its pattern is conditional.

## 噪音机器人 / Noisebot (`noisebot`)

- 类型：normal；区域：特殊/未知
- 特性：Encounter: special/unknown; HP 18-23; ascension HP 19-24. Pattern (cycle): Always uses Noise. Utility/special moves: Noise (Status: Status).
- 简略攻略：Keep draw and mitigation available for status/debuff turns instead of overcommitting setup.

## 奥斯提 / Osty (`osty`)

- 类型：normal；区域：特殊/未知
- 特性：Encounter: special/unknown; HP 1; ascension HP not listed. Utility/special moves: Nothing (Unknown: Unknown).
- 简略攻略：This is a special encounter entity; follow its live intent and legal actions.

## 直飞产卵虫 / Ovicopter (`ovicopter`)

- 类型：normal；区域：Act 2 - Hive
- 特性：Encounter: Act 2 - Hive; HP 124-130; ascension HP 126-132. Pattern (conditional): Starts: Lay Eggs → Smash → Tenderizer; then conditional: Lay Eggs (if can lay) / Nutritional Paste (if cannot lay). Peak listed attack: Smash 16 (ascension 17). Utility/special moves: Lay Eggs (Summon: Minion +1 to self); Tenderizer (Attack + Debuff: Tenderizer 7 (ascension 8), Vulnerable +2 to player); Nutritional Paste (Buff: Strength +3 to self).
- 简略攻略：Do not allow summons to multiply pressure; prioritize the summoner or the most dangerous add. Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Re-check the live intent every turn because its pattern is conditional.

## 猫头鹰法官 / Owl Magistrate (`owl_magistrate`)

- 类型：normal；区域：Act 3 - Glory
- 特性：Encounter: Act 3 - Glory; HP 231; ascension HP 247. Pattern (cycle): Magistrate Scrutiny → Peck Assault → Judicial Flight → Verdict → repeat. Peak listed attack: Verdict 33 (ascension 36). Utility/special moves: Judicial Flight (Buff: Soar +1 to self); Verdict (Attack + Debuff: Verdict 33 (ascension 36), Vulnerable +4 to player).
- 简略攻略：Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks. Plan a dedicated Block, Weak, or lethal turn for Verdict; it is the peak listed hit.

## 佩尔的士兵 / Pael's Legion (`paels_legion`)

- 类型：normal；区域：特殊/未知
- 特性：Encounter: special/unknown; HP 9999; ascension HP not listed. Utility/special moves: Nothing (Unknown: Unknown).
- 简略攻略：This is a special encounter entity; follow its live intent and legal actions.

## 寄生惧魔 / Parafright (`parafright`)

- 类型：normal；区域：Act 2 - Hive
- 特性：Encounter: Act 2 - Hive; HP 21; ascension HP not listed. Pattern (cycle): Always uses Slam. Peak listed attack: Slam 16 (ascension 17). Innate: Illusion 1: When this dies, it revives next turn at full HP.
- 简略攻略：Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 花园幽灵鳗 / Phantasmal Gardener (`phantasmal_gardener`)

- 类型：elite；区域：Act 1 - Underdocks
- 特性：Encounter: Act 1 - Underdocks; HP 26-31; ascension HP 27-32. Pattern (conditional): then conditional: Flail (if in first slot) / Bite (if in second slot) / Lash (if in third slot) / Enlarge (if in fourth slot). Peak listed attack: Lash 7 (ascension 7). Innate: Skittish 6: The first time this creature is hit each turn, it gains  Block. Utility/special moves: Enlarge (Buff: Strength +2 to self).
- 简略攻略：Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks. Re-check the live intent every turn because its pattern is conditional.

## 异蛙寄生虫 / Phrog Parasite (`phrog_parasite`)

- 类型：elite；区域：Act 1 - Overgrowth
- 特性：Encounter: Act 1 - Overgrowth; HP 61-64; ascension HP 66-68. Pattern (random): Starts: Infect → Lash. Peak listed attack: Lash 4x4 (ascension 5x4). Innate: Infested 4: Upon dying, summons... something. Utility/special moves: Infect (Status: Status).
- 简略攻略：Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks. Re-check the live intent every turn because its pattern is random.

## 拳击构装体 / Punch Construct (`punch_construct`)

- 类型：normal；区域：Act 1 - Underdocks, Act 3 - Glory
- 特性：Encounter: Act 1 - Underdocks, Act 3 - Glory; HP 55; ascension HP 60. Peak listed attack: Strong Punch 14 (ascension 16). Innate: Artifact 1: Negates debuffs. Utility/special moves: READY (Defend: Block 10); Fast Punch (Attack + Debuff: Fast Punch 5x2 (ascension 6x2), Frail +1 to player).
- 简略攻略：Strip Artifact before relying on an important Weak, Vulnerable, or other debuff. Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks.

## 女王 / Queen (`queen`)

- 类型：boss；区域：Act 3 - Glory
- 特性：Encounter: Act 3 - Glory; HP 400; ascension HP 419. Pattern (conditional): Starts: Puppet Strings → You Are Mine; then conditional: Burn Bright for Me (if does not have amalgam died) / Off with Your Head (if has amalgam died); then conditional: Burn Bright for Me (if does not have amalgam died) / Off with Your Head (if has amalgam died). Peak listed attack: Off with Your Head 3x5 (ascension 4x5). Utility/special moves: Puppet Strings (Debuff: Chains of Binding +3 to player); You Are Mine (Debuff: Frail +99 to player, Weak +99 to player, Vulnerable +99 to player); Burn Bright for Me (Buff + Defend: Block 20); Enrage (Buff: Strength +2 to self).
- 简略攻略：Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks. Re-check the live intent every turn because its pattern is conditional.

## 火箭 / Rocket (`rocket`)

- 类型：boss；区域：Act 2 - Hive
- 特性：Encounter: Act 2 - Hive; HP 199; ascension HP 209. Pattern (cycle): Targeting Reticle → Precision Beam → Charge Up → Laser → Recharge → repeat. Peak listed attack: Laser 31 (ascension 35). Innate: Back Attack 1: Deals 50% more damage when it is attacking you from behind; Crab Rage 1: When an ally dies, this creature gains 6 Strength and 99 Block. Utility/special moves: Charge Up (Buff: Strength +2 to self); Recharge (Sleep: Sleep).
- 简略攻略：Plan a dedicated Block, Weak, or lethal turn for Laser; it is the peak listed hit. Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 咬人卷轴 / Scroll of Biting (`scroll_of_biting`)

- 类型：normal；区域：Act 3 - Glory
- 特性：Encounter: Act 3 - Glory; HP 30-37; ascension HP 33-39. Peak listed attack: Chomp 14 (ascension 16). Innate: Paper Cuts 2: Whenever this creature deals unblocked attack damage to you, you lose  Max HP. Utility/special moves: More Teeth (Buff: Strength +2 to self).
- 简略攻略：Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks. Re-check the live intent every turn because its pattern is random.

## 海洋混混 / Seapunk (`seapunk`)

- 类型：normal；区域：Act 1 - Underdocks
- 特性：Encounter: Act 1 - Underdocks; HP 44-46; ascension HP 47-49. Pattern (cycle): Sea Kick → Spinning Kick → Bubble Burp → repeat. Peak listed attack: Sea Kick 11 (ascension 13). Utility/special moves: Bubble Burp (Buff + Defend: Block 7, Strength +1 to self).
- 简略攻略：Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks. Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 下水道蚌 / Sewer Clam (`sewer_clam`)

- 类型：normal；区域：Act 1 - Underdocks
- 特性：Encounter: Act 1 - Underdocks; HP 56; ascension HP 58. Peak listed attack: Jet 10 (ascension 11). Utility/special moves: Pressurize (Buff: Strength +4 to self).
- 简略攻略：Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 缩小甲虫 / Shrinker Beetle (`shrinker_beetle`)

- 类型：normal；区域：Act 1 - Overgrowth
- 特性：Encounter: Act 1 - Overgrowth; HP 38-40; ascension HP 40-42. Pattern (cycle): Shrinker → Chomp → Stomp → repeat. Peak listed attack: Stomp 13 (ascension 14). Utility/special moves: Shrinker (Debuff: Debuff).
- 简略攻略：Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 鬼祟珊瑚群 / Skulking Colony (`skulking_colony`)

- 类型：elite；区域：Act 1 - Underdocks
- 特性：Encounter: Act 1 - Underdocks; HP 75; ascension HP 80. Pattern (cycle): Zoom → Zoom Move 2 → Inertia → Piercing Stabs → repeat. Peak listed attack: Zoom 14 (ascension 16). Innate: Hardened Shell 20: This creature cannot lose more than  HP each turn. Utility/special moves: Inertia (Attack + Buff: Inertia 9 (ascension 11), Strength +2 to self).
- 简略攻略：Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks. Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 史莱姆狂战士 / Slimed Berserker (`slimed_berserker`)

- 类型：normal；区域：Act 3 - Glory
- 特性：Encounter: Act 3 - Glory; HP 261; ascension HP 281. Pattern (cycle): Always uses Vomit Ichor. Peak listed attack: Smother 30 (ascension 33). Utility/special moves: Vomit Ichor (Status: Status); Leeching Hug (Debuff + Buff: Weak +3 to player, Strength +3 to self).
- 简略攻略：Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks. Plan a dedicated Block, Weak, or lethal turn for Smother; it is the peak listed hit.

## 蛇行扼杀者 / Slithering Strangler (`slithering_strangler`)

- 类型：normal；区域：Act 1 - Overgrowth
- 特性：Encounter: Act 1 - Overgrowth; HP 53-55; ascension HP 54-56. Pattern (random): Starts with Constrict. Peak listed attack: Lash 12 (ascension 13). Utility/special moves: Constrict (Debuff: Constrict +3 to player); Thwack (Attack + Defend: Thwack 7 (ascension 8), Block 5).
- 简略攻略：Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Re-check the live intent every turn because its pattern is random.

## 淤泥旋螺 / Sludge Spinner (`sludge_spinner`)

- 类型：normal；区域：Act 1 - Underdocks
- 特性：Encounter: Act 1 - Underdocks; HP 37-39; ascension HP 41-42. Pattern (random): Starts with Oil Spray. Peak listed attack: Slam 11 (ascension 12). Utility/special moves: Oil Spray (Attack + Debuff: Oil Spray 8 (ascension 9), Weak +1 to player); Rage (Attack + Buff: Rage 6 (ascension 7), Strength +3 to self).
- 简略攻略：Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Re-check the live intent every turn because its pattern is random.

## 熟睡甲虫 / Slumbering Beetle (`slumbering_beetle`)

- 类型：normal；区域：Act 2 - Hive
- 特性：Encounter: Act 2 - Hive; HP 86; ascension HP 89. Pattern (conditional): Starts with Snore. Peak listed attack: Roll Out 16 (ascension 18). Innate: Plating 15: At the end of your turn, gain  Block. Plating is reduced by 1 at the start of your turn; Slumber 3: Awakens upon taking turns or losing HP 3 times. Utility/special moves: Snore (Sleep: Sleep); Roll Out (Attack + Buff: Roll Out 16 (ascension 18), Strength +2 to self).
- 简略攻略：Use safe sleeping turns to set up, then commit damage when ready for the wake-up pattern. Re-check the live intent every turn because its pattern is conditional.

## 闪光贾克斯果 / Snapping Jaxfruit (`snapping_jaxfruit`)

- 类型：normal；区域：Act 1 - Overgrowth
- 特性：Encounter: Act 1 - Overgrowth; HP 31-33; ascension HP 34-36. Pattern (cycle): Always uses Energy Orb. Peak listed attack: Energy Orb 3 (ascension 4). Utility/special moves: Energy Orb (Attack + Buff: Energy Orb 3 (ascension 4), Strength +2 to self).
- 简略攻略：Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 卑鄙地精 / Sneaky Gremlin (`sneaky_gremlin`)

- 类型：normal；区域：Act 1 - Underdocks
- 特性：Encounter: Act 1 - Underdocks; HP 10-14; ascension HP 11-15. Pattern (cycle): Always uses Wake Up. Peak listed attack: Tackle 9 (ascension 10). Utility/special moves: Wake Up (Stun: Stun).
- 简略攻略：Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 灵魂异鱼 / Soul Fysh (`soul_fysh`)

- 类型：boss；区域：Act 1 - Underdocks
- 特性：Encounter: Act 1 - Underdocks; HP 211; ascension HP 221. Pattern (cycle): Beckon → De-Gas → Gaze → Fade → Scream → repeat. Peak listed attack: De-Gas 16 (ascension 18). Utility/special moves: Beckon (Status: Status); Fade (Buff: Intangible +2 to self); Scream (Attack + Debuff: Scream 13 (ascension 15), Vulnerable +3 to player).
- 简略攻略：Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 灵魂枢纽 / Soul Nexus (`soul_nexus`)

- 类型：elite；区域：Act 3 - Glory
- 特性：Encounter: Act 3 - Glory; HP 234; ascension HP 254. Pattern (random): Starts with Soul Burn; then random: Soul Burn (no repeat), Maelstrom (no repeat), Drain Life (no repeat). Peak listed attack: Soul Burn 29 (ascension 31). Utility/special moves: Drain Life (Attack + Debuff: Drain Life 18 (ascension 19), Vulnerable +2 to player, Weak +2 to player).
- 简略攻略：Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks. Plan a dedicated Block, Weak, or lethal turn for Soul Burn; it is the peak listed hit.

## 幽灵骑士 / Spectral Knight (`spectral_knight`)

- 类型：elite；区域：Act 3 - Glory
- 特性：Encounter: Act 3 - Glory; HP 93; ascension HP 97. Pattern (random): Starts: Hex → Soul Slash. Peak listed attack: Soul Slash 15 (ascension 17). Utility/special moves: Hex (Debuff: Hex +2 to self).
- 简略攻略：Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks. Re-check the live intent every turn because its pattern is random.

## 棘刺蟾蜍 / Spiny Toad (`spiny_toad`)

- 类型：normal；区域：Act 2 - Hive
- 特性：Encounter: Act 2 - Hive; HP 116-119; ascension HP 121-124. Pattern (cycle): Protruding Spikes → Spike Explosion → Tongue Lash → repeat. Peak listed attack: Spike Explosion 23 (ascension 25). Utility/special moves: Protruding Spikes (Buff: Thorns +5 to self).
- 简略攻略：Plan a dedicated Block, Weak, or lethal turn for Spike Explosion; it is the peak listed hit. Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 戳刺机器人 / Stabbot (`stabbot`)

- 类型：normal；区域：特殊/未知
- 特性：Encounter: special/unknown; HP 18-23; ascension HP 19-24. Pattern (cycle): Always uses Stab. Peak listed attack: Stab 11 (ascension 12). Utility/special moves: Stab (Attack + Debuff: Stab 11 (ascension 12), Frail +1 to player).
- 简略攻略：Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 骇鳗 / Terror Eel (`terror_eel`)

- 类型：elite；区域：Act 1 - Underdocks
- 特性：Encounter: Act 1 - Underdocks; HP 140; ascension HP 150. Pattern (cycle): Crash → Thrash → repeat. Peak listed attack: Crash 16 (ascension 18). Innate: Shriek 70: The first time this creature's HP reaches  or below, it becomes Stunned. Utility/special moves: Thrash (Attack + Buff: Thrash 3x3 (ascension 4x3), Vigor +6 to self); Stun (Stun: Stun); Terrorize (Debuff: Vulnerable +99 to player).
- 简略攻略：Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks. Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 实验体 #C14 / Test Subject #C14 (`test_subject`)

- 类型：boss；区域：Act 3 - Glory
- 特性：Encounter: Act 3 - Glory; HP not listed; ascension HP not listed. Pattern (conditional): Starts: Bite → Skull Bash; then conditional: Multi-Claw (if respawns < 2) / Lacerate (if respawns >= 2). Peak listed attack: Big Pounce 45. Innate: Adaptable 1: When this creature would be defeated, it instead revives even stronger; Enrage 2: Whenever you play a Skill, gains 2 Strength. Utility/special moves: Respawn (Heal + Buff: Painful Stabs +1 to self, Nemesis +1 to self); Skull Bash (Attack + Debuff: Skull Bash 14 (ascension 16), Vulnerable +1 to player); Burning Growl (Status + Buff: Strength +2 to self).
- 简略攻略：Budget damage and resources for its revive instead of treating the first lethal as the end. Save enough burst to outpace or finish through its listed healing turn. Keep draw and mitigation available for status/debuff turns instead of overcommitting setup.

## 对手1型 / The Adversary Mk 1 (`the_adversary_mk_one`)

- 类型：normal；区域：特殊/未知
- 特性：Encounter: special/unknown; HP 100; ascension HP not listed. Pattern (cycle): Smash → Beam → Barrage → repeat. Peak listed attack: Barrage 8x2. Innate: Artifact 0: Negates debuffs. Utility/special moves: Barrage (Attack + Buff: Barrage 8x2, Strength +2 to self).
- 简略攻略：Strip Artifact before relying on an important Weak, Vulnerable, or other debuff. Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks. Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 对手3型 / The Adversary Mk 3 (`the_adversary_mk_three`)

- 类型：normal；区域：特殊/未知
- 特性：Encounter: special/unknown; HP 300; ascension HP 300. Pattern (cycle): Crash → Flame Beam → Barrage → repeat. Peak listed attack: Barrage 10x2. Innate: Artifact 2: Negates debuffs. Utility/special moves: Barrage (Attack + Buff: Barrage 10x2, Strength +4 to self).
- 简略攻略：Strip Artifact before relying on an important Weak, Vulnerable, or other debuff. Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks. Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 对手2型 / The Adversary Mk 2 (`the_adversary_mk_two`)

- 类型：normal；区域：特殊/未知
- 特性：Encounter: special/unknown; HP 200; ascension HP 200. Pattern (cycle): Bash → Flame Beam → Barrage → repeat. Peak listed attack: Barrage 9x2. Innate: Artifact 1: Negates debuffs. Utility/special moves: Barrage (Attack + Buff: Barrage 9x2, Strength +3 to self).
- 简略攻略：Strip Artifact before relying on an important Weak, Vulnerable, or other debuff. Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks. Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 遗忘之物 / The Forgotten (`the_forgotten`)

- 类型：normal；区域：Act 3 - Glory
- 特性：Encounter: Act 3 - Glory; HP 106; ascension HP 111. Pattern (cycle): Always uses Miasma. Innate: Possess Speed 1: When killed, return all stolen Dexterity to the player. Utility/special moves: Miasma (Debuff + Defend + Buff: Block 8, Dexterity +2 to self); Dread (Attack: Attack).
- 简略攻略：Keep draw and mitigation available for status/debuff turns instead of overcommitting setup.

## 无厌沙虫 / The Insatiable (`the_insatiable`)

- 类型：boss；区域：Act 2 - Hive
- 特性：Liquify Ground starts Sandpit: when its live countdown expires, the player is eaten and dies. Encounter: Act 2 - Hive; HP 321; ascension HP 341. Pattern (cycle): Liquify Ground → Thrash → Lunging Bite → Salivate → Thrash Move 2 → repeat. Peak listed attack: Lunging Bite 28 (ascension 31). Utility/special moves: Liquify Ground (Buff + Status: Buff + Status); Salivate (Buff: Strength +2 to self).
- 简略攻略：When sandpit_power is at 1, play the bound frantic_escape card before spending its energy; never end the turn while that escape is playable. Preserve at least 1 energy and do not exhaust frantic_escape while the Sandpit countdown is active. Prepare Block or Weak for Lunging Bite and finish before repeated Strength buffs compound.

## 失落之物 / The Lost (`the_lost`)

- 类型：normal；区域：Act 3 - Glory
- 特性：Encounter: Act 3 - Glory; HP 93; ascension HP 99. Pattern (cycle): Always uses Debilitating Smog. Peak listed attack: Eye Lasers 4x2 (ascension 5x2). Innate: Possess Strength 1: When killed, return all stolen Strength to the player. Utility/special moves: Debilitating Smog (Debuff + Buff: Strength +2 to self).
- 简略攻略：Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks. Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 胧光怪 / The Obscura (`the_obscura`)

- 类型：normal；区域：Act 2 - Hive
- 特性：Encounter: Act 2 - Hive; HP 123; ascension HP 129. Pattern (random): Starts with Illusion. Peak listed attack: Piercing Gaze 10 (ascension 11). Utility/special moves: Illusion (Summon: Summon); Sail (Buff: Buff); Hardening Strike (Attack + Defend: Hardening Strike 6 (ascension 7), Block 6).
- 简略攻略：Do not allow summons to multiply pressure; prioritize the summoner or the most dangerous add. Re-check the live intent every turn because its pattern is random.

## 偷窃草蜢 / Thieving Hopper (`thieving_hopper`)

- 类型：normal；区域：Act 2 - Hive
- 特性：Encounter: Act 2 - Hive; HP 79; ascension HP 84. Pattern (cycle): Thievery → Flutter → Hat Trick → Nab → Escape → repeat. Peak listed attack: Hat Trick 21 (ascension 23). Innate: Escape Artist 5: Tries to escape the combat after 2 turns. Utility/special moves: Flutter (Buff: Flutter +5 to self); Escape (Escape: Escape).
- 简略攻略：Front-load damage if allowing its escape would lose rewards or prolong the encounter. Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 蟾蜍蝌蚪 / Toadpole (`toadpole`)

- 类型：normal；区域：Act 1 - Underdocks
- 特性：Encounter: Act 1 - Underdocks; HP 21-25; ascension HP 22-26. Pattern (conditional): then conditional: Whirl (if not in front) / Spiken (if in front). Peak listed attack: Spike Spit 3x3 (ascension 4x3). Utility/special moves: Spiken (Buff: Thorns +2 to self).
- 简略攻略：Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks. Re-check the live intent every turn because its pattern is conditional.

## 火炬头聚合体 / Torch Head Amalgam (`torch_head_amalgam`)

- 类型：boss；区域：Act 3 - Glory
- 特性：Encounter: Act 3 - Glory; HP 199; ascension HP 211. Pattern (cycle): Strong Tackle → Tackle 2 → Beam → Tackle 3 → Tackle 4 → repeat. Peak listed attack: Strong Tackle 26 (ascension 32). Innate: Minion 1: Minions abandon combat without their leader.
- 简略攻略：Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks. Plan a dedicated Block, Weak, or lethal turn for Strong Tackle; it is the peak listed hit. Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 结实的卵 / Tough Egg (`tough_egg`)

- 类型：normal；区域：Act 2 - Hive
- 特性：Encounter: Act 2 - Hive; HP 14-18; ascension HP 15-19. Pattern (cycle): Always uses Hatch. Peak listed attack: Nibble 4 (ascension 5). Utility/special moves: Hatch (Summon: Summon).
- 简略攻略：Do not allow summons to multiply pressure; prioritize the summoner or the most dangerous add. Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 劫掠者追踪手 / Tracker Raider (`tracker_ruby_raider`)

- 类型：normal；区域：Act 1 - Overgrowth
- 特性：Encounter: Act 1 - Overgrowth; HP 21-25; ascension HP 22-26. Pattern (cycle): Always uses Track. Peak listed attack: Unleash the Hounds 1x8 (ascension 1x8). Utility/special moves: Track (Debuff: Frail +2 to player).
- 简略攻略：Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks. Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 地道虫 / Tunneler (`tunneler`)

- 类型：normal；区域：Act 2 - Hive
- 特性：Encounter: Act 2 - Hive; HP 87; ascension HP 92. Pattern (cycle): Bite → Burrow → Attack from Below → repeat. Peak listed attack: Attack from Below 23 (ascension 26). Utility/special moves: Burrow (Buff + Defend: Block 32, Burrowed +1 to self); Dizzy (Stun: Stun).
- 简略攻略：Plan a dedicated Block, Weak, or lethal turn for Attack from Below; it is the peak listed hit. Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 高塔炮手 / Turret Operator (`turret_operator`)

- 类型：normal；区域：Act 3 - Glory
- 特性：Encounter: Act 3 - Glory; HP 41; ascension HP 51. Pattern (cycle): Unload! → Unload Move 2 → Reload → repeat. Peak listed attack: Unload! 3x5 (ascension 4x5). Utility/special moves: Reload (Buff: Strength +1 to self).
- 简略攻略：Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks. Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 树枝史莱姆（中） / Twig Slime (M) (`twig_slime_m`)

- 类型：normal；区域：Act 1 - Overgrowth
- 特性：Encounter: Act 1 - Overgrowth; HP 26-28; ascension HP 27-29. Pattern (random): Starts with Sticky Shot. Peak listed attack: Pokey Pounce 11 (ascension 12). Utility/special moves: Sticky Shot (Status: Status).
- 简略攻略：Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Re-check the live intent every turn because its pattern is random.

## 树枝史莱姆（小） / Twig Slime (S) (`twig_slime_s`)

- 类型：normal；区域：Act 1 - Overgrowth
- 特性：Encounter: Act 1 - Overgrowth; HP 7-11; ascension HP 8-12. Pattern (cycle): Always uses Tackle. Peak listed attack: Tackle 4 (ascension 5).
- 简略攻略：Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 双尾鼠 / Two-Tailed Rat (`two_tailed_rat`)

- 类型：normal；区域：Act 1 - Underdocks
- 特性：Encounter: Act 1 - Underdocks; HP 17-21; ascension HP 18-22. Peak listed attack: Scratch 8 (ascension 9). Utility/special moves: Screech (Debuff: Frail +1 to player); Call for Backup (Summon: Summon).
- 简略攻略：Do not allow summons to multiply pressure; prioritize the summoner or the most dangerous add. Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Re-check the live intent every turn because its pattern is random.

## 墨影幻灵 / Vantom (`vantom`)

- 类型：boss；区域：Act 1 - Overgrowth
- 特性：Encounter: Act 1 - Overgrowth; HP 173; ascension HP 183. Pattern (cycle): Ink Blot → Inky Lance → Dismember → Prepare → repeat. Peak listed attack: Dismember 26 (ascension 30). Innate: Slippery 8: The next 2 times this creature loses HP, it only loses 1 HP instead. Utility/special moves: Prepare (Buff: Strength +2 to self).
- 简略攻略：Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks. Plan a dedicated Block, Weak, or lethal turn for Dismember; it is the peak listed hit.

## 藤蔓蹒跚者 / Vine Shambler (`vine_shambler`)

- 类型：normal；区域：Act 1 - Overgrowth
- 特性：Encounter: Act 1 - Overgrowth; HP 61; ascension HP 64. Pattern (cycle): Swipe → Grasping Vines → Chomp → repeat. Peak listed attack: Chomp 16 (ascension 18). Utility/special moves: Grasping Vines (Attack + Debuff: Grasping Vines 8 (ascension 9), Tangled +1 to player).
- 简略攻略：Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks. Use the listed cycle to prepare mitigation one turn before its dangerous attack.

## 瀑布巨兽 / Waterfall Giant (`waterfall_giant`)

- 类型：boss；区域：Act 1 - Underdocks
- 特性：Its special sequence includes About to Blow followed by Explode. Encounter: Act 1 - Underdocks; HP 240; ascension HP 250. Pattern (cycle): Pressurize → Stomp → Ram → Siphon → Pressure Gun → Pressure Up → repeat. Peak listed attack: Stomp 15 (ascension 16). Utility/special moves: Pressurize (Buff: Steam Eruption +15 to self); Stomp (Attack + Debuff + Buff: Stomp 15 (ascension 16), Weak +1 to player, Steam Eruption +3 to self); Ram (Attack + Buff: Ram 10 (ascension 11), Steam Eruption +3 to self); Siphon (Heal + Buff: Steam Eruption +3 to self).
- 简略攻略：Treat About to Blow as the final setup window: secure lethal or maximum mitigation before Explode.

## 扭动虫 / Wriggler (`wriggler`)

- 类型：elite；区域：Act 1 - Overgrowth
- 特性：Encounter: Act 1 - Overgrowth; HP 17-21; ascension HP 18-22. Peak listed attack: Nasty Bite 6 (ascension 7). Utility/special moves: Wriggle (Buff + Status: Strength +2 to self); Spawned (Stun: Stun).
- 简略攻略：Keep draw and mitigation available for status/debuff turns instead of overcommitting setup. Re-check the live intent every turn because its pattern is conditional.

## 电击机器人 / Zapbot (`zapbot`)

- 类型：normal；区域：特殊/未知
- 特性：Encounter: special/unknown; HP 18-23; ascension HP 19-24. Pattern (cycle): Always uses Zap. Peak listed attack: Zap 14 (ascension 15). Innate: High Voltage 2: At the end of this creature's turn, it gains  Strength.
- 简略攻略：Use the listed cycle to prepare mitigation one turn before its dangerous attack.
