use std::fmt;
use std::simd::{num::SimdFloat, Simd};
use std::sync::OnceLock;

/// Maximum accepted vector dimension, bounding per-call work to 4 MiB per input.
pub const MAX_DIMENSIONS: usize = 1_048_576;

type Kernel = fn(&[u8], &[u8]) -> Result<f64, VectorError>;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum VectorError {
    Empty,
    InvalidLength,
    DimensionMismatch,
    TooManyDimensions,
    NonFinite,
    ZeroNorm,
}

impl fmt::Display for VectorError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            Self::Empty => "vectors must contain at least one f32",
            Self::InvalidLength => "BLOB byte length must be a multiple of four",
            Self::DimensionMismatch => "vector dimensions must match",
            Self::TooManyDimensions => "vector dimension exceeds 1048576",
            Self::NonFinite => "vector elements must be finite",
            Self::ZeroNorm => "cosine distance is undefined for zero-norm vectors",
        })
    }
}

impl std::error::Error for VectorError {}

#[derive(Clone, Copy)]
struct Kernels {
    cosine: Kernel,
    l2: Kernel,
}

static KERNELS: OnceLock<Kernels> = OnceLock::new();

fn kernels() -> &'static Kernels {
    KERNELS.get_or_init(|| {
        #[cfg(target_arch = "x86_64")]
        if std::is_x86_feature_detected!("avx2") {
            return Kernels {
                cosine: |a, b| unsafe { avx2::<true>(a, b) },
                l2: |a, b| unsafe { avx2::<false>(a, b) },
            };
        }
        Kernels {
            cosine: compute::<true>,
            l2: compute::<false>,
        }
    })
}

fn validate(a: &[u8], b: &[u8]) -> Result<(), VectorError> {
    if a.is_empty() || b.is_empty() {
        return Err(VectorError::Empty);
    }
    if a.len() % 4 != 0 || b.len() % 4 != 0 {
        return Err(VectorError::InvalidLength);
    }
    if a.len() != b.len() {
        return Err(VectorError::DimensionMismatch);
    }
    if a.len() / 4 > MAX_DIMENSIONS {
        return Err(VectorError::TooManyDimensions);
    }
    Ok(())
}

/// Returns cosine distance for equally sized, nonempty little-endian f32 BLOBs.
///
/// Rejects non-finite elements, zero norms, and dimensions above `MAX_DIMENSIONS`.
pub fn cosine_distance(a: &[u8], b: &[u8]) -> Result<f64, VectorError> {
    validate(a, b)?;
    (kernels().cosine)(a, b)
}

/// Returns squared Euclidean distance for little-endian f32 BLOBs.
///
/// Rejects empty, malformed, mismatched, non-finite, or oversized inputs.
pub fn l2_squared_distance(a: &[u8], b: &[u8]) -> Result<f64, VectorError> {
    validate(a, b)?;
    (kernels().l2)(a, b)
}

#[inline(always)]
fn read_lane(bytes: &[u8], offset: usize) -> f32 {
    f32::from_le_bytes([
        bytes[offset],
        bytes[offset + 1],
        bytes[offset + 2],
        bytes[offset + 3],
    ])
}

#[inline(always)]
fn load(bytes: &[u8]) -> Simd<f64, 8> {
    Simd::<f32, 8>::from_array(std::array::from_fn(|i| read_lane(bytes, i * 4))).cast()
}

#[inline(always)]
fn compute<const COSINE: bool>(a: &[u8], b: &[u8]) -> Result<f64, VectorError> {
    let mut sums = [Simd::<f64, 8>::splat(0.0); 2];
    let mut norms_a = [Simd::<f64, 8>::splat(0.0); 2];
    let mut norms_b = [Simd::<f64, 8>::splat(0.0); 2];
    let (chunks_a, tail_a) = a.as_chunks::<64>();
    let (chunks_b, tail_b) = b.as_chunks::<64>();
    for (a_chunk, b_chunk) in chunks_a.iter().zip(chunks_b) {
        for i in 0..2 {
            let x = load(&a_chunk[i * 32..]);
            let y = load(&b_chunk[i * 32..]);
            if COSINE {
                sums[i] += x * y;
                norms_a[i] += x * x;
                norms_b[i] += y * y;
            } else {
                let delta = x - y;
                sums[i] += delta * delta;
            }
        }
    }
    let mut total = (sums[0] + sums[1]).reduce_sum();
    let mut norm_a = (norms_a[0] + norms_a[1]).reduce_sum();
    let mut norm_b = (norms_b[0] + norms_b[1]).reduce_sum();
    for (x, y) in tail_a
        .as_chunks::<4>()
        .0
        .iter()
        .zip(tail_b.as_chunks::<4>().0)
    {
        let x = f64::from(read_lane(x, 0));
        let y = f64::from(read_lane(y, 0));
        if COSINE {
            total += x * y;
            norm_a += x * x;
            norm_b += y * y;
        } else {
            let delta = x - y;
            total += delta * delta;
        }
    }
    if !total.is_finite() || (COSINE && (!norm_a.is_finite() || !norm_b.is_finite())) {
        return Err(VectorError::NonFinite);
    }
    if COSINE {
        if norm_a == 0.0 || norm_b == 0.0 {
            return Err(VectorError::ZeroNorm);
        }
        Ok((1.0 - total / (norm_a.sqrt() * norm_b.sqrt())).clamp(0.0, 2.0))
    } else {
        Ok(total)
    }
}

#[cfg(target_arch = "x86_64")]
#[target_feature(enable = "avx2")]
unsafe fn avx2<const COSINE: bool>(a: &[u8], b: &[u8]) -> Result<f64, VectorError> {
    compute::<COSINE>(a, b)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn blob(values: &[f32]) -> Vec<u8> {
        values.iter().flat_map(|x| x.to_le_bytes()).collect()
    }

    #[test]
    fn known_distances() {
        let a = blob(&[1.0, 0.0]);
        assert_eq!(cosine_distance(&a, &a), Ok(0.0));
        assert_eq!(cosine_distance(&a, &blob(&[-1.0, 0.0])), Ok(2.0));
        assert_eq!(cosine_distance(&a, &blob(&[0.0, 1.0])), Ok(1.0));
        assert_eq!(l2_squared_distance(&a, &blob(&[4.0, 4.0])), Ok(25.0));
    }

    #[test]
    fn rejects_invalid_inputs() {
        assert_eq!(cosine_distance(&[], &[]), Err(VectorError::Empty));
        assert_eq!(
            l2_squared_distance(&[0; 3], &[0; 3]),
            Err(VectorError::InvalidLength)
        );
        assert_eq!(
            l2_squared_distance(&[0; 4], &[0; 8]),
            Err(VectorError::DimensionMismatch)
        );
        assert_eq!(
            cosine_distance(&[0; 4], &[0; 4]),
            Err(VectorError::ZeroNorm)
        );
        let oversized = vec![0; (MAX_DIMENSIONS + 1) * 4];
        assert_eq!(
            l2_squared_distance(&oversized, &oversized),
            Err(VectorError::TooManyDimensions)
        );
        for bad in [f32::NAN, f32::INFINITY, f32::NEG_INFINITY] {
            for position in [0, 7, 15, 16, 30] {
                let mut values = vec![1.0; 31];
                values[position] = bad;
                let a = blob(&values);
                assert_eq!(l2_squared_distance(&a, &a), Err(VectorError::NonFinite));
                assert_eq!(cosine_distance(&a, &a), Err(VectorError::NonFinite));
            }
        }
    }

    #[test]
    fn extreme_finite_values_remain_finite() {
        for value in [f32::MAX, f32::MIN_POSITIVE, f32::from_bits(1)] {
            let a = blob(&[value; 33]);
            let b = blob(&[-value; 33]);
            assert!((cosine_distance(&a, &a).unwrap()).abs() < 1e-14);
            assert!((cosine_distance(&a, &b).unwrap() - 2.0).abs() < 1e-14);
            let expected = 33.0 * (2.0 * f64::from(value)).powi(2);
            let actual = l2_squared_distance(&a, &b).unwrap();
            assert!((actual - expected).abs() <= expected * 1e-14);
        }
    }

    #[test]
    fn simd_and_tails_match_scalar_with_unaligned_storage() {
        for dim in (1..=65).chain([127, 128, 129, 384, 768, 1536, 4097]) {
            let a: Vec<f32> = (0..dim)
                .map(|i| ((i * 17 % 101) as f32 - 50.0) / 13.0)
                .collect();
            let b: Vec<f32> = (0..dim)
                .map(|i| ((i * 23 % 97) as f32 - 48.0) / 19.0)
                .collect();
            let mut bytes_a = vec![0u8];
            bytes_a.extend(blob(&a));
            let mut bytes_b = vec![0u8; 3];
            bytes_b.extend(blob(&b));
            let mut dot = 0.0;
            let mut aa = 0.0;
            let mut bb = 0.0;
            let mut l2 = 0.0;
            for (&x, &y) in a.iter().zip(&b) {
                let (x, y) = (f64::from(x), f64::from(y));
                dot += x * y;
                aa += x * x;
                bb += y * y;
                l2 += (x - y).powi(2);
            }
            let cos = (1.0 - dot / (aa.sqrt() * bb.sqrt())).clamp(0.0, 2.0);
            let x = &bytes_a[1..];
            let y = &bytes_b[3..];
            assert!((l2_squared_distance(x, y).unwrap() - l2).abs() <= l2 * 1e-12);
            assert!((cosine_distance(x, y).unwrap() - cos).abs() < 1e-12);
            assert!((compute::<false>(x, y).unwrap() - l2).abs() <= l2 * 1e-12);
            assert!((compute::<true>(x, y).unwrap() - cos).abs() < 1e-12);
        }
    }
}
