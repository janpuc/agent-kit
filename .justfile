python := "python3"

default:
    @just --list

vendor *ARGS:
    {{python}} scripts/vendor.py {{ARGS}}

lock:
    {{python}} scripts/lock.py

lock-check:
    {{python}} scripts/lock.py --check

build:
    {{python}} scripts/build.py

verify:
    {{python}} scripts/verify.py

package:
    {{python}} scripts/package.py

release: build verify package

check:
    koment check
    koment comments check
    koment agents check

ci: lock-check build verify check
