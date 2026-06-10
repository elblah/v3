#!/bin/bash

SCRIPT_FILE=$(readlink -f $0)

AICODER_MODELS_FILE=/run/user/$UID/tmp/data/models
AICODER_MODEL_CURRENT_FILE=/run/user/$UID/tmp/model.cur

if [ ! -e "$AICODER_MODELS_FILE" ]; then
    # NOTE: aicoder-gen-models is not provided by aicoder and 
    #       should be implemented by the user
    echo "No models file found... execute aicoder-gen-models"
    exit 1
fi

MODELS=$(<$AICODER_MODELS_FILE)

if [[ "$@" =~ --list ]]; then
    MODEL=$(echo "$MODELS" | fzf -e)
    if [ -z "$MODEL" ]; then
        exit 1
    fi
    IFS=";" read -r API_MODEL CONTEXT_SIZE PROVIDER API_BASE_URL API_KEY API_PROVIDER _ <<< "$MODEL"
    printf '%s\n' \
        "API_MODEL=$API_MODEL" \
        "CONTEXT_SIZE=$CONTEXT_SIZE" \
        "API_BASE_URL=$API_BASE_URL" \
        "API_KEY=$API_KEY" \
        "API_PROVIDER=$API_PROVIDER" \
        > "$AICODER_MODEL_CURRENT_FILE"
    #sleep 1
    exit
fi

tmux display-popup -E "$SCRIPT_FILE --list"
ret=$?
if [ "$ret" != 0 ]; then
    exit 1
fi
cat $AICODER_MODEL_CURRENT_FILE
rm -f '$AICODER_MODEL_CURRENT_FILE'
