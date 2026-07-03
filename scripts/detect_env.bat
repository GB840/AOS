@echo off
IF "%KUBERNETES_SERVICE_HOST%"=="" (
  echo standalone
) ELSE (
  echo cluster
)