#!/usr/bin/env fish

function multifind
    find . $argv
    find ../hdx/rainhdx $argv
end

set ignore \( \
    -name flake.lock -o \
    -name .git -o \
    -name build -o \
    -name .\?\* -o \
    -name \*.pyc -o \
    -name __pycache__ -o \
    -name \*.o -o \
    -name \*.exe -o \
    -name \*.bin -o \
    -path \*/template/\* -o \
    -false \
\)

set rtl \( \
    -path \*/rtl/__init__.py -o \
    -path \*/rtl/mmu.py -o \
    -path \*/rtl/rv32.py -o \
    -path \*/rtl/uart/\* -o \
    -false \
\)

set test \( \
    -name st.py -o \
    -path \*/formal/\* -o \
    -name test_\* -o \
    -path \*/lluvia/\*.[cs] -o \
    -path \*/lluvia/\*.ld -o \
    -path \*/lluvia/Makefile -o \
    -path \*/rainhdx/formal.py -o \
    -path \*/rainhdx/test.py -o \
    -path \*/rainhdx/fixtures/__init__.py -o \
    -false \
\)

set other \( \
    -path \*/sae/__init__.py -o \
    -path \*/sae/__main__.py -o \
    -name pyproject.toml -o \
    -name flake.nix -o \
    -name default.nix -o \
    -path \*/rainhdx/build.py -o \
    -name \*.fish -o \
    -path \*/rainhdx/__init__.py -o \
    -path \*/rainhdx/logger.py -o \
    -path \*/rainhdx/platform.py -o \
    -false \
\)

echo RTL:
multifind $ignore -prune -o $rtl -print | xargs wc -l
echo

echo Test:
multifind \( $ignore -o $rtl \) -prune -o $test -print | xargs wc -l
echo

echo Other:
multifind \( $ignore -o $rtl -o $test \) -prune -o $other -print | xargs wc -l


set rest (multifind \( $ignore -o $rtl -o $test -o $other \) -prune -o -type f -print)
if test (count $rest) -gt 0
    echo
    echo Uncategorised:
    echo $rest
end

echo
printf 'Total: %d\n' (multifind $ignore -prune -o -type f -print | xargs wc -l --total=only)
printf '(ignoring %d files)\n' (multifind $ignore -type f | wc -l)
