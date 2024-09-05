# Build qpdf dependency
export QPDF_SOURCE_TREE="$SRC"/qpdf
export QPDF_BUILD_LIBDIR=$QPDF_SOURCE_TREE/build/libqpdf
export CLANG_PATH=$(which clang)
export CLANGXX_PATH=$(which clang++)
export CC=$CLANG_PATH
export CXX=$CLANGXX_PATH

cd $QPDF_SOURCE_TREE
cmake -S . -B build \
    -DCMAKE_BUILD_TYPE=RelWithDebInfo \
    -DBUILD_SHARED_LIBS=ON \
    -DCMAKE_C_COMPILER="$CLANG_PATH" \
    -DCMAKE_CXX_COMPILER="$CLANGXX_PATH" \
    -DCMAKE_C_FLAGS="-fsanitize=address,fuzzer-no-link" \
    -DCMAKE_CXX_FLAGS="-fsanitize=address,fuzzer-no-link -std=c++17" \
    -DCMAKE_EXE_LINKER_FLAGS="$CLANGXX_PATH -shared" \
    -DCMAKE_CXX_STANDARD=17 \
    -DCMAKE_VERBOSE_MAKEFILE=ON
cmake --build build --parallel --target libqpdf
cp $QPDF_SOURCE_TREE/build/libqpdf/libqpdf.so.29 /usr/lib
ldconfig

# Build pikepdf
cd "$SRC"/pikepdf
env QPDF_SOURCE_TREE=$QPDF_SOURCE_TREE QPDF_BUILD_LIBDIR=$QPDF_BUILD_LIBDIR \
    CC="$CLANG_PATH" CFLAGS="-fsanitize=address,fuzzer-no-link" CXX="$CLANGXX_PATH" CXXFLAGS="-fsanitize=address,fuzzer-no-link" LDSHARED="$CLANGXX_PATH -shared" \
    pip3 install --verbose -e .


# Build fuzzers in $OUT
for fuzzer in $(find fuzzing -name '*_fuzzer.py');do
  compile_python_fuzzer "$fuzzer" --add-binary="/src/qpdf/build/libqpdf/libqpdf.so.29:/usr/lib"
done
zip -q $OUT/pikepdf_fuzzer_seed_corpus.zip $SRC/pikepdf/fuzzing/corpus/*
