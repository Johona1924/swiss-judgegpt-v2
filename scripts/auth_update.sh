 #!/bin/sh

AZURE_USE_AUTHENTICATION=$(azd env get-value AZURE_USE_AUTHENTICATION)
USE_APPSERVICE_AUTHENTICATION=$(azd env get-value USE_APPSERVICE_AUTHENTICATION)

if [ "$USE_APPSERVICE_AUTHENTICATION" = "true" ]; then
  echo "USE_APPSERVICE_AUTHENTICATION is set to true. Skipping Microsoft Entra application updates."
  exit 0
fi

if [ "$AZURE_USE_AUTHENTICATION" != "true" ]; then
  exit 0
fi

. ./scripts/load_python_env.sh

./.venv/bin/python ./scripts/auth_update.py
