# brand-days

把大陆餐饮/零售品牌的**周期性优惠**（肯德基疯狂星期四、每月 8 号零食会员日这类）
变成手机日历里**每晚 20:00 准时弹出的提醒**。

一份人工核对过的优惠数据集，加一个生成 `.ics` 的小工具。
不需要推送服务，不需要注册，除了 PyYAML 和 icalendar 没有别的依赖。

> ⚠️ **本项目没有爬虫，也不是优惠聚合站。**
> 数据全部由人工逐条核对（核对记录见 [`data/pending.yaml`](data/pending.yaml)），
> 每条都带来源和核对日期，覆盖度有限。只收**周期可预测**的优惠；
> 限时秒杀、随机发券这类不放进来，它们在日历上看不出价值。

## 用法

### 方式一：订阅日历（推荐，一次点击）

把下面这个地址粘进支持"订阅日历 / 通过 URL 添加日历"的客户端：

```
https://cdn.jsdelivr.net/gh/Adler862/brand-days@main/deals.ics
```

Google 日历、Apple 日历、Outlook、Thunderbird 都支持这种方式，数据会自动更新。

> 选 jsDelivr 是因为 `raw.githubusercontent.com` 在国内多数网络不可达。
> jsDelivr 有约 12 小时缓存，改数据后不会立刻生效。

### 方式二：导入 ics（国产手机日历）

**国产 ROM 的自带日历普遍只能导入、不能订阅**（没有订阅入口，也没有 CalDAV 组件），
数据不会自动更新。为此本项目把生成窗口设为 **365 天**，一年重导 0~2 次就够了，
不必为了绕过客户端限制去装额外的 App。

导入方式：下载 [`deals.ics`](deals.ics) → 用日历 App 打开 → 导入。

> 重复导入**不会去重**：Android 日历在导入时丢弃事件 UID，
> 同一份文件导入两次会得到两份重复事件（实测 35 条 → 70 条）。
> 建议先建一个**专属日历**再导入，刷新时删掉整个日历重新导入。
> 详见[已知限制](#已知限制)。

> ⚠️ **导入时留意目标日历。** vivo 日历默认选中"本地日历"，
> 它的导入界面也没有可以预置目标日历的参数，这一步只能手动选对。
> 万一选错了不用重新导入，用 `tools/move_to_calendar.py --to 优惠提醒` 批量搬过去。

### 方式三：自己生成

Windows（PowerShell）：

```powershell
git clone https://github.com/Adler862/brand-days.git
cd brand-days
python -m pip install -r requirements.txt
python gen.py                 # data/*.yaml -> deals.ics
python tools/test_gen.py      # 周期规则与边界自测
python tools/check_ics.py     # ics 结构校验（时区/VALARM/折叠/长度）
```

Linux / macOS：

```bash
git clone https://github.com/Adler862/brand-days.git && cd brand-days
python3 -m pip install -r requirements.txt
python3 gen.py
```

分开写两份是因为：`&&` 在 PowerShell 5.1 里不是合法连接符；
`python` 在部分 Linux/macOS 发行版上要写成 `python3`。

改 `data/offers.yaml` 加你自己的店，或改 `config.yaml` 调整窗口与提醒时刻。

## 功能

- **自带一个网页**：[`index.html`](index.html) 是自包含的单文件（没有 CDN、框架和外部字体），
  双击就能看：默认显示"今天"，可以搜索全部数据，并分栏展示已确认 / 待核实 / 时效型三类。
  生成 `deals.ics` 时会一并生成它。
- **每晚 20:00 提醒次日优惠**：提醒放在晚上，你才有时间提前安排。
- **每天一条全天摘要兜底**：万一手机不弹 `VALARM` 通知，翻日历仍能看到今天有什么。
- **显式内嵌 `VTIMEZONE`**：`icalendar` 默认只写 `TZID=Asia/Shanghai` 这个*引用*，
  不写时区定义块。解析不出时区 ID 的客户端会让事件**整体偏移 8 小时，且不报任何错**。
  本项目把定义块一并写入，已在真机验证无偏移。
- **生成具体事件，不用 `RRULE`**：RRULE 表达不了"某周停办""同一天两个时段"这类真实情况。
  硬套 RRULE 就得另外维护一份 `EXDATE` 例外清单，代码反而更长。详见 [SPEC.md](SPEC.md)。
- **按 tier 与 confidence 筛选**：`tier: core | extended` 决定是否进日历，
  `confidence: verified | unverified` 决定是否可信。不筛选的话每周会往日历里塞 30+ 条事件，
  结果是整个日历被静音。噪音一多，核心的那几条也跟着被忽略。

## 数据

`data/` 下三个文件，职责不重叠：

| 文件 | 内容 | 是否进日历 |
|---|---|---|
| [`offers.yaml`](data/offers.yaml) | 已核实的周期性优惠 | ✅ 仅 `verified` + `tier: core` |
| [`pending.yaml`](data/pending.yaml) | 待核实线索（查无此据 / 与素材不符） | ❌ 永不 |
| [`oneoff.yaml`](data/oneoff.yaml) | 时效型优惠（抢券类） | ❌ 只作文档保留 |

一条记录长这样：

```yaml
- id: kfc-crazy-thursday          # 稳定标识，改名会在订阅端产生重复事件
  brand: 肯德基
  offer: 疯狂星期四
  recur: { type: weekly, days: [thu] }    # weekly 按星期；monthly 按每月几号
  window: { start: "09:30", end: "23:00" } # 绑时段的优惠必须写，否则提醒时刻会错
  tier: core                     # core 进日历；extended 只留在数据里
  confidence: verified           # unverified 永不进日历
  conditions:
    - 堂食 9:30-23:00，外送 9:15-22:44
    - 单品 9.9 / 19.9 / 29.9 元，全国限量
  source: "https://m.bendibao.com/show954854.html"
  verified_at: 2026-10-15        # 超过 90 天会在网页上标记待复核
```

当前收录 **8 条**（7 条 `core` + 1 条 `extended`）：

| 品牌 | 周期 | 优惠 | 备注 |
|---|---|---|---|
| 肯德基 | 每周四 | 疯狂星期四 | 有堂食/外送时段与全国限量 |
| 麦当劳 | 每周一 | 麦麦省，App 领 7 张券 | **不是半价** |
| 必胜客 | 每周三 | 尖叫星期三，指定品买一送一 | 需会员 |
| 塔斯汀 | 每周二 | +1 元双份 | 仅堂食/小程序，外卖不参与 |
| 海底捞 | 每周三 | 会员日领菜品券 | 须消费满 80 元 |
| 好想来 | 每月 8 号 | 会员日 88 折 | — |
| 赵一鸣零食 | 每月 8 号 | 会员日 88 折 | 特价品不参与 |
| 达美乐 | 每周二/三/四 | 原价比萨七折 | 限 3 种饼底、仅指定城市（故列为 `extended`） |

## 配置

`config.yaml` 的常用项：

| 项 | 默认 | 说明 |
|---|---|---|
| `window_days` | `365` | 生成多少天。**改小之前请先读 [SPEC.md](SPEC.md) 的 §0.2** |
| `remind_at` | `"20:00"` | 每晚提醒时刻 |
| `digest` | `true` | 是否生成全天摘要兜底事件 |
| `tiers_in_calendar` | `[core]` | 哪些 tier 进日历 |
| `phone_calendar_name` | `"优惠提醒"` | 手机上专属日历名，供 `tools/refresh_on_phone.py` 定位 |
| `base_url` | jsDelivr 地址 | 对外分发地址，换用户名会导致所有订阅链接失效 |

## 工具

`tools/` 下的脚本都在真机上跑过：

| 脚本 | 作用 |
|---|---|
| `test_gen.py` | 周期规则、跨年、窗口边界的自测 |
| `check_ics.py` | ics 结构校验：内嵌时区、VALARM、折叠 ≤75 字节、末尾 CRLF |
| `check_html.py` | 网页校验：自包含性、内联 JSON、**用最小 DOM 在 node 里真跑一遍渲染**、数字与数据一致 |
| `roundtrip_ics.py` | 用标准解析器读回，验证折叠无损 |
| `make_test_ics.py` | 生成几分钟后触发的测试日历，当场验证 `VALARM` 是否真会弹通知 |
| `verify_on_phone.py` | 通过 adb 读手机日历数据库，与 `deals.ics` 逐条比对 |
| `verify_subscribe.py` | 验证手机能否从 CDN 取回 ics 并正确处理 |
| `refresh_on_phone.py` | 清空**专属日历**并重新导入，绝不触碰个人日程 |
| `move_to_calendar.py` | 把事件迁移到指定日历（导入时选错日历的补救） |

理由：**ics 生成正确不等于手机上正确**。客户端的时区解析、全天事件存储、
提醒入库、换行容忍度，只能拿真实数据去验。本项目在真机上抓到 4 个只有实测才会暴露的问题。

## 已知限制

- **数据覆盖度低。** 目前 8 条，`pending.yaml` 里还有 18 条待核实线索。
  这个项目的价值主要在数据上，而数据只能一条条核对出来。
- **`extended` 条目不进日历。** 这是有意的：每周 30+ 条事件会让整个日历被静音。
  想要更全就改 `config.yaml` 的 `tiers_in_calendar`。
- **国产手机日历不能订阅，且导入会丢 UID。** 重复导入会产生重复事件，
  建议用专属日历，刷新时整个日历删掉重导。这是 Android 日历存储层的行为，
  换客户端大概率也绕不过去。
- **偶尔会有误报。** 商家停办、改规则、临时调整都可能发生。
  `source` 与 `verified_at` 两个字段就是为定位这类问题准备的。
- **只收周期可预测的优惠。** 限时秒杀、随机发券不在范围内。
- **只在 vivo 自带日历（Android 16）上做过真机验证。** 其他客户端的兼容性靠 ics 标准保证，
  没有实测过。

## 素材来源与核对

初始素材来自微信截图，溯源后发现问题：那是 **2024-11-11 一篇自媒体汇总的三次转抄**，
里面有不少抄录错误（把某品牌的活动排到错误的星期、同一条重复出现两次等）。

60 条素材的核对结果：

| 类别 | 数量 | 处理 |
|---|---|---|
| 高置信度可直接采用 | 8 | 进 `offers.yaml` |
| 查证后需改写 | 4+ | 改写或移入 `pending.yaml` |
| 完全查无此据 | 9 | 进 `pending.yaml` |
| 存疑待核实 | 其余 | 进 `pending.yaml` |

全部核对记录都留在 `pending.yaml`，欢迎补充或纠错。

## License

MIT，见 [LICENSE](LICENSE)。数据同样以 MIT 提供，欢迎 fork 与 PR。
