#!/bin/zsh
# Gives the call review its own long-lived Claude sign-in. Run it once; again only if the review
# says the sign-in has expired (it lasts about a year).
#
# 1. `claude setup-token` opens the browser; approve it, and it prints a token in this window.
# 2. Copy that token, then paste it at the hidden prompt below. It's saved to ~/.config/call-review/claude-token,
#    readable only by your account. Nothing else stores or shows it.

unset ANTHROPIC_BASE_URL
~/.local/bin/claude setup-token || { echo "setup-token didn't finish. Run this script again."; exit 1; }
echo
read -rs "token?Paste the token you just copied, then press Return (it won't show): "
echo
if [[ -z "$token" ]]; then echo "Nothing pasted, nothing saved."; exit 1; fi
mkdir -p ~/.config/call-review && chmod 700 ~/.config/call-review
umask 077
printf %s "$token" > ~/.config/call-review/claude-token
chmod 600 ~/.config/call-review/claude-token
unset token
clear; printf "\033[3J"                                   # also wipe the scrollback, where the token was printed
echo "Saved. The call review now has its own sign-in. You can close this tab."
