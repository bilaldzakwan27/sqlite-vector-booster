use sqlite_vector_booster::vector::{cosine_distance, l2_squared_distance};
use std::hint::black_box;
use std::time::Instant;

type Operation = fn(&[u8], &[u8]) -> f64;

fn scalar(a: &[u8], b: &[u8], cosine: bool) -> f64 {
    let mut sum = 0.0;
    let mut norm_a = 0.0;
    let mut norm_b = 0.0;
    for (x, y) in a.as_chunks::<4>().0.iter().zip(b.as_chunks::<4>().0) {
        let x = f64::from(f32::from_le_bytes(*x));
        let y = f64::from(f32::from_le_bytes(*y));
        if cosine {
            sum += x * y;
            norm_a += x * x;
            norm_b += y * y;
        } else {
            sum += (x - y) * (x - y);
        }
    }
    if cosine {
        (1.0 - sum / (norm_a.sqrt() * norm_b.sqrt())).clamp(0.0, 2.0)
    } else {
        sum
    }
}

fn measure(operation: Operation, a: &[u8], b: &[u8], iterations: usize) -> f64 {
    for _ in 0..1000 {
        black_box(operation(black_box(a), black_box(b)));
    }
    let mut samples = Vec::with_capacity(7);
    for _ in 0..7 {
        let start = Instant::now();
        for _ in 0..iterations {
            black_box(operation(black_box(a), black_box(b)));
        }
        samples.push(start.elapsed().as_secs_f64() * 1e9 / iterations as f64);
    }
    samples.sort_by(f64::total_cmp);
    samples[3]
}

fn main() {
    let operations: [(&str, &str, Operation); 4] = [
        ("simd", "cosine", |a, b| cosine_distance(a, b).unwrap()),
        ("scalar", "cosine", |a, b| scalar(a, b, true)),
        ("simd", "l2_squared", |a, b| {
            l2_squared_distance(a, b).unwrap()
        }),
        ("scalar", "l2_squared", |a, b| scalar(a, b, false)),
    ];
    println!("backend,metric,dimensions,iterations,median_ns_per_pair,million_pairs_per_second,input_gb_per_second");
    for dim in [128, 384, 768, 1536] {
        let a: Vec<u8> = (0..dim)
            .flat_map(|i| ((i % 97) as f32 / 97.0).to_le_bytes())
            .collect();
        let b: Vec<u8> = (0..dim)
            .flat_map(|i| ((i % 89) as f32 / 89.0).to_le_bytes())
            .collect();
        let iterations = 100_000;
        for (backend, metric, operation) in operations {
            let ns = measure(operation, &a, &b, iterations);
            println!(
                "{backend},{metric},{dim},{iterations},{ns:.3},{:.3},{:.3}",
                1000.0 / ns,
                (dim * 8) as f64 / ns
            );
        }
    }
}
