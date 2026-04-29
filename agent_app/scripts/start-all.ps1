# 在 agent_app 目录执行：.\scripts\start-all.ps1
Set-Location (Join-Path $PSScriptRoot "..")
npm install
npm run dev
