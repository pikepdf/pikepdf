# SPDX-FileCopyrightText: 2024 ennamarie19
# SPDX-License-Identifier: MIT
export QPDF_SOURCE_TREE="$SRC"/qpdf
export QPDF_BUILD_LIBDIR=$QPDF_SOURCE_TREE/build/libqpdf

# Build qpdf dependency
cd $QPDF_SOURCE_TREE
cmake -S . -B build \
    -DOSS_FUZZ=ON \
    -DBUILD_SHARED_LIBS=ON \
    -DCMAKE_BUILD_TYPE=Debug \
    -DCMAKE_CXX_STANDARD=17 \
    CC="$CC" CXX="$CXX" CFLAGS="$CFLAGS" CXXFLAGS="$CXXFLAGS"
cmake --build build --parallel --target libqpdf

# Build pikepdf
cd "$SRC"/pikepdf
env QPDF_SOURCE_TREE=$QPDF_SOURCE_TREE QPDF_BUILD_LIBDIR=$QPDF_BUILD_LIBDIR \
    CC="$CC" CFLAGS="$CFLAGS" CXX="$CXX" CXXFLAGS="$CXXFLAGS" LDSHARED="$CXX -shared" \
    pip3 install --verbose .


# Build fuzzers in $OUT
for fuzzer in $(find fuzzing -name '*_fuzzer.py');do
  compile_python_fuzzer "$fuzzer" \
      --add-binary="/src/qpdf/build/libqpdf/libqpdf.so.30:." \
      --add-binary="/lib/x86_64-linux-gnu/libz.so.1:." \
      --add-binary="/lib/x86_64-linux-gnu/libjpeg.so.8:."
done
zip -q $OUT/pikepdf_fuzzer_seed_corpus.zip $SRC/pikepdf/fuzzing/corpus/*
