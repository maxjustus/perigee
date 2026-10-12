use std::ffi::{CStr, c_char, c_void};
use std::process::ExitCode;
use std::thread;
use std::time::{Duration, Instant};

const REGISTERS: [(&str, u32); 5] = [
    ("ID", 0x00),
    ("GENERAL", 0x0C),
    ("STATUS", 0x10),
    ("INTERRUPT", 0x14),
    ("INFO", 0x68),
];

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("probe: {e}");
            ExitCode::FAILURE
        }
    }
}

fn run() -> Result<(), String> {
    let probe: fn(&Device) -> Result<(), String> = match std::env::args().nth(1).as_deref() {
        Some("regs") => regs,
        Some("ring") => ring,
        _ => return Err("usage: probe regs|ring".into()),
    };
    probe(&Device::open(c"com_apogeedigital_Ensemble2Device")?)
}

fn regs(device: &Device) -> Result<(), String> {
    for (name, offset) in REGISTERS {
        println!("{offset:#06x} {name:<9} {:#010x}", device.read(offset)?);
    }
    Ok(())
}

const RING_FRAMES: u32 = 0x4000;
const OUT_CHANNELS: u32 = 36;
const IN_CHANNELS: u32 = 34;
const INPUT_AUDIO_ADDRESS_LOW: u32 = 0x30;
const CUR_INPUT_AUDIO_ADDRESS_LOW: u32 = 0x38;
const OUTPUT_AUDIO_ADDRESS_LOW: u32 = 0x44;
const CUR_OUTPUT_AUDIO_ADDRESS_LOW: u32 = 0x4C;

// The device stops the hardware when the client closes.
fn ring(device: &Device) -> Result<(), String> {
    let output = Ring {
        base: device.read(OUTPUT_AUDIO_ADDRESS_LOW)?,
        bytes: OUT_CHANNELS * RING_FRAMES * 4,
    };
    let input = Ring {
        base: device.read(INPUT_AUDIO_ADDRESS_LOW)?,
        bytes: IN_CHANNELS * RING_FRAMES * 4,
    };
    device.start(2)?;
    let start = Instant::now();
    let (mut outputs, mut inputs) = (Vec::new(), Vec::new());
    while start.elapsed() < Duration::from_secs(5) {
        let t = start.elapsed().as_nanos() as u64;
        outputs.push((t, device.read(CUR_OUTPUT_AUDIO_ADDRESS_LOW)?));
        inputs.push((t, device.read(CUR_INPUT_AUDIO_ADDRESS_LOW)?));
        thread::sleep(Duration::from_millis(1));
    }
    for (name, ring, channels, trace) in [
        ("output", output, OUT_CHANNELS, outputs),
        ("input", input, IN_CHANNELS, inputs),
    ] {
        let summary = summarize(ring, channels * 4, &trace);
        println!("{name} base {:#010x} {summary:?}", ring.base);
    }
    Ok(())
}

#[derive(Clone, Copy)]
struct Ring {
    base: u32,
    bytes: u32,
}

#[derive(Debug, PartialEq)]
struct Summary {
    out_of_range: usize,
    backward: usize,
    wraps: usize,
    frames_per_sec: f64,
    step_gcd: u32,
}

fn summarize(ring: Ring, frame_bytes: u32, trace: &[(u64, u32)]) -> Summary {
    let (inside, outside): (Vec<_>, Vec<_>) = trace
        .iter()
        .map(|&(t, address)| (t, address.wrapping_sub(ring.base)))
        .partition(|&(_, offset)| offset < ring.bytes);
    let mut s = Summary {
        out_of_range: outside.len(),
        backward: 0,
        wraps: 0,
        frames_per_sec: 0.0,
        step_gcd: 0,
    };
    let mut advanced = 0u64;
    for pair in inside.windows(2) {
        let (prev, next) = (pair[0].1, pair[1].1);
        let step = (next + ring.bytes - prev) % ring.bytes;
        if step > ring.bytes / 2 {
            s.backward += 1;
            continue;
        }
        s.wraps += usize::from(next < prev);
        advanced += u64::from(step);
        s.step_gcd = gcd(s.step_gcd, step);
    }
    if let [(first, _), .., (last, _)] = inside[..] {
        s.frames_per_sec = advanced as f64 / f64::from(frame_bytes) / ((last - first) as f64 / 1e9);
    }
    s
}

fn gcd(a: u32, b: u32) -> u32 {
    if b == 0 { a } else { gcd(b, a % b) }
}

struct Device {
    connect: u32,
}

impl Device {
    fn open(class: &CStr) -> Result<Self, String> {
        let service = unsafe { IOServiceGetMatchingService(0, IOServiceMatching(class.as_ptr())) };
        if service == 0 {
            return Err(format!("no {class:?} in the IORegistry"));
        }
        let mut connect = 0;
        let kr = unsafe { IOServiceOpen(service, mach_task_self_, 0, &mut connect) };
        unsafe { IOObjectRelease(service) };
        if kr != 0 {
            return Err(format!("IOServiceOpen: {kr:#010x}"));
        }
        Ok(Self { connect })
    }

    fn start(&self, depth: u32) -> Result<(), String> {
        const START_HARDWARE: u32 = 2;
        self.call(START_HARDWARE, &[depth], &mut [])
            .map_err(|kr| format!("start: {kr:#010x}"))
    }

    fn read(&self, offset: u32) -> Result<u32, String> {
        const ACCESS_BAR0_REGISTER: u32 = 6;
        const READ: u32 = 1;
        let mut value = [0];
        self.call(ACCESS_BAR0_REGISTER, &[READ, offset, 0], &mut value)
            .map_err(|kr| format!("read {offset:#06x}: {kr:#010x}"))?;
        checked(value[0])
    }

    fn call(&self, selector: u32, input: &[u32], output: &mut [u32]) -> Result<(), i32> {
        let mut size = size_of_val(output);
        let kr = unsafe {
            IOConnectCallStructMethod(
                self.connect,
                selector,
                input.as_ptr().cast(),
                size_of_val(input),
                output.as_mut_ptr().cast(),
                &mut size,
            )
        };
        if kr == 0 { Ok(()) } else { Err(kr) }
    }
}

impl Drop for Device {
    fn drop(&mut self) {
        unsafe { IOServiceClose(self.connect) };
    }
}

fn checked(value: u32) -> Result<u32, String> {
    match value {
        u32::MAX => Err("register reads 0xffffffff: device gone".into()),
        v => Ok(v),
    }
}

#[link(name = "IOKit", kind = "framework")]
unsafe extern "C" {
    static mach_task_self_: u32;
    fn IOServiceMatching(name: *const c_char) -> *mut c_void;
    fn IOServiceGetMatchingService(main_port: u32, matching: *mut c_void) -> u32;
    fn IOServiceOpen(service: u32, owning_task: u32, kind: u32, connect: *mut u32) -> i32;
    fn IOServiceClose(connect: u32) -> i32;
    fn IOObjectRelease(object: u32) -> i32;
    fn IOConnectCallStructMethod(
        connection: u32,
        selector: u32,
        input: *const c_void,
        input_size: usize,
        output: *mut c_void,
        output_size: *mut usize,
    ) -> i32;
}

#[cfg(test)]
mod tests {
    use super::*;

    const RING: Ring = Ring {
        base: 0x1000,
        bytes: 1000,
    };

    fn trace(offsets: &[u32]) -> Vec<(u64, u32)> {
        offsets
            .iter()
            .enumerate()
            .map(|(i, &o)| (i as u64 * 1_000_000, RING.base + o))
            .collect()
    }

    #[test]
    fn steady_pointer_wraps_and_gives_the_rate() {
        let s = summarize(RING, 4, &trace(&[0, 400, 800, 200, 600]));
        assert_eq!(
            s,
            Summary {
                out_of_range: 0,
                backward: 0,
                wraps: 1,
                frames_per_sec: 100_000.0,
                step_gcd: 400,
            }
        );
    }

    #[test]
    fn backward_and_out_of_range_pointers_are_counted() {
        let s = summarize(RING, 4, &trace(&[0, 400, 300, 2000]));
        assert_eq!((s.backward, s.out_of_range), (1, 1));
    }

    #[test]
    fn all_ones_means_the_device_is_gone() {
        assert_eq!(checked(0x1234_5678), Ok(0x1234_5678));
        assert!(checked(u32::MAX).is_err());
    }
}
