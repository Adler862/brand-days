# brand-days

把大陆餐饮/零售品牌的**周期性优惠**（肯德基疯狂星期四、每月 8 号零食会员日这类）
变成手机日历里**每晚 20:00 准时弹出的提醒**。

一份人工核对的优惠数据集 + 一个生成 `.ics` 的小工具。**零推送服务、零第三方依赖、零注册。**

> ⚠️ **这不是爬虫项目，也不是优惠聚合站。**
> 数据来自人工逐条核对（核对记录见 [`data/pending.yaml`](data/pending.yaml)），
> 覆盖度有限但每条都标注了来源和核对日期。目前只收录**周期可预测**的优惠 ——
> 限时秒杀、随机发券这类故意不收，因为它们在日历里没有意义。

## 用法

### 方式一：订阅日历（推荐，一次点击）

把下面这个地址粘进支持"订阅日历 / 通过 URL 添加日历"的客户端：

```
https://cdn.jsdelivr.net/gh/Adler862/brand-days@main/deals.ics
```

Google 日历、Apple 日历、Outlook、Thunderbird 都支持这种方式，数据会自动更新。

> 走 jsDelivr 而不是 `raw.githubusercontent.com`，是因为后者在国内多数网络不可达。
> jsDelivr 有约 12 小时缓存，改数据后不会立刻生效。

### 方式二：导入 ics（国产手机日历）

**国产 ROM 的自带日历普遍只能导入、不能订阅**（无订阅入口、无 CalDAV 组件），
也就是说数据不会自动更新。本项目为此把生成窗口设为 **365 天**，
让"一年重导 0~2 次"成为可接受的方案，而不是为了绕过客户端限制去要求你装额外的 App。

导入方式：下载 [`deals.ics`](deals.ics) → 用日历 App 打开 → 导入。

> 重复导入**不会去重**：Android 日历在导入时丢弃事件 UID，
> 同一份文件导入两次会得到两份重复事件（实测 35 条 → 70 条）。
> 所以务必先建一个**专属日历**再导入，刷新时删掉整个日历重新导入。
> 详见[已知限制](#已知限制)。

> ⚠️ **导入时注意目标日历。** vivo 日历会默认选中"本地日历"，
> 而且它的导入界面不暴露任何可预置目标日历的参数 —— 也就是说这一步只能手动选对。
> 万一选错了，不用重新导入，用 `tools/move_to_calendar.py --to 优惠提醒` 批量搬过去即可。

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

两处刻意分开写：`&&` 在 PowerShell 5.1 里不是合法连接符，
而 `python` 在部分 Linux/macOS 发行版上需要写成 `python3`。

改 `data/offers.yaml` 加你自己的店，或改 `config.yaml` 调整窗口与提醒时刻。

## 功能

- **自带一个网页**：[`index.html`](index.html) 是自包含的单文件（无 CDN、无框架、无外部字体），
  双击就能看：默认显示"今天"，可搜索全部数据，并分栏展示已确认 / 待核实 / 时效型三类。
  生成 `deals.ics` 时会一并生成它。
- **每晚 20:00 提醒次日优惠**：规划类提醒的价值在前一晚，不是当天凌晨。20:00 是你还醒着且能决策的时刻。
- **每天一条全天摘要兜底**：万一手机不弹 `VALARM` 通知，翻日历仍能看到今天有什么。
- **显式内嵌 `VTIMEZONE`**：`icalendar` 默认只写 `TZID=Asia/Shanghai` 这个*引用*而不写定义块，
  猜不出时区 ID 的客户端会让事件**整体偏移 8 小时且不报错**。本项目显式内嵌，已真机验证无偏移。
- **生成具体事件而非 `RRULE`**：RRULE 表达不了"某周停办""同一天两个时段"这类真实情况，
  硬用只会把裁剪逻辑挪进 `EXDATE` 例外清单，代码更长。详见 [SPEC.md](SPEC.md)。
- **分级筛选**：`tier: core | extended` 决定是否进日历，`confidence: verified | unverified` 决定是否可信。
  不筛选的话每周会往日历里塞 30+ 条事件，结果是被整体静音 —— **噪音的代价不是信息多，是核心信息陪葬**。

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

`tools/` 下的脚本都做过真机验证，不是摆设：

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

理由：**ics 生成正确 ≠ 手机上正确**。客户端的时区解析、全天事件存储、提醒入库、
换行容忍度只能靠真实数据验证。本项目在真机上抓到了 4 个只有实测才会暴露的问题。

## 已知限制

- **数据覆盖度低。** 目前 8 条，`pending.yaml` 里还有 18 条待核实线索。
  这个项目的价值在数据而不在代码，而数据只能一条条核对出来。
- **`extended` 条目不进日历。** 这是刻意的：每周 30+ 条事件会让日历被整体静音。
  想要更全？改 `config.yaml` 的 `tiers_in_calendar` 自己加。
- **国产手机日历不能订阅，且导入会丢 UID。** 重复导入产生重复事件，
  因此建议用专属日历 + 整日历删除重导。这是 Android 日历存储层的行为，换客户端大概率无解。
- **偶尔会有误报。** 商家停办、改规则、临时调整都可能发生，`source` 与 `verified_at`
  就是为定位这类问题准备的。
- **仅收录周期可预测的优惠。** 限时秒杀、随机发券不在范围内。
- **只在 vivo 自带日历（Android 16）上做过真机验证。** 其他客户端的兼容性靠 ics 标准保证，
  未经实测。

## 素材来源与核对

本项目的初始素材来自微信截图收集，溯源后发现是 **2024-11-11 一篇自媒体汇总的三次转抄**，
含大量抄录错误（把某品牌的活动排到错误的星期、同一条重复出现两次等）。

60 条素材的核对结果：

| 类别 | 数量 | 处理 |
|---|---|---|
| 高置信度可直接采用 | 8 | 进 `offers.yaml` |
| 查证后需改写 | 4+ | 改写或移入 `pending.yaml` |
| 完全查无此据 | 9 | 进 `pending.yaml` |
| 存疑待核实 | 其余 | 进 `pending.yaml` |

**这件事不是打击，是立项理由** —— 它说明中文互联网上没人对这类信息做核对工作，
连一份流传一年的汇总都是错的。核对记录全部保留在 `pending.yaml`，欢迎补充或纠错。

## License

MIT，见 [LICENSE](LICENSE)。数据同样以 MIT 提供，欢迎 fork 与 PR。
