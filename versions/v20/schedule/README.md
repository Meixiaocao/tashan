# 定时评审的挂法

**边界先写清**：定时只做两件事——跑取证脚本、留下"待评审"标记。**判断、分级、外部对照必须由人或有 agent 在场时执行**。无人值守时他山不会自己下结论。

---

## 一、对象清单

编辑 `targets.txt`，每行一个绝对路径，`#` 开头为注释：

```
D:/work/project-a
D:/work/project-b
```

## 二、一键跑一遍

```bash
bash schedule/tick.sh            # 读 targets.txt，逐个取证
bash schedule/tick.sh --dry-run  # 只打印将要处理的目录
```

产出：

- `<对象>/评审/evidence/evidence-*.json`（三份证据，覆盖更新）
- `<对象>/评审/PENDING.md`（待评审标记，含证据时间戳与下一步）

## 三、挂成定时

### Windows 任务计划

```powershell
schtasks /Create /TN "他山周检" /SC WEEKLY /D MON /ST 09:00 ^
  /TR "bash \"C:\Users\<你>\.agents\skills\他山\schedule\tick.sh\""
```

查：`schtasks /Query /TN "他山周检"`；删：`schtasks /Delete /TN "他山周检" /F`。

### 类 Unix（cron）

```
0 9 * * 1 bash "$HOME/.agents/skills/他山/schedule/tick.sh" >> "$HOME/.agents/skills/他山/schedule/tick.log" 2>&1
```

### 中台派单

把 `tick.sh` 的产出接到任务队列：`PENDING.md` 出现即为一条"待评审"任务，派给有 agent 的会话执行 `他山 <路径> <维度>`。

## 四、推荐的触发时机

| 时机 | 理由 |
|---|---|
| 版本发布前 | 差距清单可直接决定这版修不修 |
| 每周一次取证 | 观察体积、文件数、依赖数的漂移 |
| 每季度一次全维 | 单维看不出架构级问题 |

## 五、已知限制

- 取证脚本只读，不会修改对象；但会在对象下写 `评审/`。对象只读时 `tick.sh` 退到临时目录。
- `tick.sh` 失败不影响对象本身，日志在 `schedule/tick.log`。
- `PENDING.md` 只是标记，不会自动触发评审；需要人或中台消费。
