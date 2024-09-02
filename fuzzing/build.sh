cd "$SRC"/pikepdf
pip3 install -r $SRC/pikepdf/fuzzing/requirements.txt
CC="`which clang`" CFLAGS="-fsanitize=address,fuzzer-no-link" CXX="`which clang++`" CXXFLAGS="-fsanitize=address,fuzzer-no-link" LDSHARED="`which clang++` -shared" pip3 install .

# Build fuzzers in $OUT
for fuzzer in $(find fuzzing -name '*_fuzzer.py');do
  compile_python_fuzzer "$fuzzer"
done
zip -q $OUT/pikepdf_fuzzer_seed_corpus.zip $SRC/pikepdf/fuzzing/corpus/*
