---
name: denetim-ayri
tags: [cekirdek, denetim]
runs: 1
max_turns: 40
timeout_seconds: 600
allowed_tools: [Bash, Read, Write, Edit, Glob, Grep, Agent, Skill]
---
Bu projede orkestra açık değilse önce `orkestra baslat` çalıştır. Sonra /orkestra:is ile şu tek işi yürüt: notlar/ozet.md dosyasına "Orkestra çalışıyor." cümlesini yaz. İş T1 basamağında olsun; çıktıyı ayrı bir denetçi onaylasın ve kartı teslim et.
