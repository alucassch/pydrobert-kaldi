#include "pydrobert/kaldi/vector.hpp"

template<typename Real>
void NumpyVector<Real>::SetData(const Real* vec_in,
                                               const kaldi::MatrixIndexT len) {
  if (kaldi::Vector<Real>::Dim() != len) {
    kaldi::Vector<Real>::Resize(len, kaldi::kUndefined);
  }
  std::memcpy(kaldi::Vector<Real>::Data(), vec_in, len * sizeof(Real));
}

template<typename Real>
bool NumpyVector<Real>::ReadDataInto(const kaldi::MatrixIndexT len,
                                                    Real* vec_inout) const {
  if (kaldi::Vector<Real>::Dim() != len) return false;
  if (!len) return true;  // empty; skip memcpy call
  std::memcpy(vec_inout, kaldi::Vector<Real>::Data(), len * sizeof(Real));
  return true;
}
