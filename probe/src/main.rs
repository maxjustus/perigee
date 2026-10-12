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
        Some("getall") => get_all,
        Some("irq") => irq,
        _ => return Err("usage: probe regs|ring|getall|irq [mask]".into()),
    };
    probe(&Device::open(c"com_apogeedigital_Ensemble2Device")?)
}

fn regs(device: &Device) -> Result<(), String> {
    for (name, offset) in REGISTERS {
        println!("{offset:#06x} {name:<9} {:#010x}", device.read(offset)?);
    }
    Ok(())
}

const INTERRUPT: u32 = 0x14;

fn irq(device: &Device) -> Result<(), String> {
    const ENABLE_TIME_STAMP: u32 = 6;
    const TIME_STAMP_PAGE: u32 = 2;
    let extra = match std::env::args().nth(2) {
        Some(mask) => u32::from_str_radix(mask.trim_start_matches("0x"), 16)
            .map_err(|e| format!("mask {mask}: {e}"))?,
        None => 0,
    };
    device.misc(ENABLE_TIME_STAMP, 1)?;
    let sample_time = device.map(TIME_STAMP_PAGE)?;
    device.start(2)?;
    let before = device.read(INTERRUPT)?;
    device.write(INTERRUPT, before | extra)?;
    let start = Instant::now();
    let (mut seen, mut times) = (0, Vec::new());
    while start.elapsed() < Duration::from_secs(2) {
        let msis = unsafe { sample_time.read_volatile() } / u64::from(RING_FRAMES);
        if msis != seen {
            times.push((start.elapsed().as_millis(), msis - seen));
            seen = msis;
        }
        thread::sleep(Duration::from_millis(1));
    }
    let during = device.read(INTERRUPT)?;
    device.write(INTERRUPT, before)?;
    println!("INTERRUPT {before:#010x} -> {during:#010x}: {seen} MSIs in 2 s");
    println!("ms (count): {times:?}");
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

const PACKET_BYTES: usize = 120;

fn get_all(device: &Device) -> Result<(), String> {
    const GET_ALL: u8 = 4;
    let port = device.notification_port()?;
    let mut request = [0u8; PACKET_BYTES];
    request[..8].copy_from_slice(&1u64.to_le_bytes());
    request[8] = GET_ALL;
    device.send(&request)?;
    let start = Instant::now();
    while let Some(packet) = receive(port, 2000)? {
        println!(
            "{:>6} ms {}",
            start.elapsed().as_millis(),
            describe(&packet)
        );
    }
    Ok(())
}

#[repr(C)]
struct Notification {
    header: [u32; 6],
    packet: [u8; PACKET_BYTES],
    trailer: [u8; 68],
}

fn receive(port: u32, timeout_ms: u32) -> Result<Option<[u8; PACKET_BYTES]>, String> {
    const MACH_RCV_MSG: i32 = 0x2;
    const MACH_RCV_TIMEOUT: i32 = 0x100;
    const MACH_RCV_TIMED_OUT: i32 = 0x1000_4003;
    let mut message = Notification {
        header: [0; 6],
        packet: [0; PACKET_BYTES],
        trailer: [0; 68],
    };
    let kr = unsafe {
        mach_msg(
            (&raw mut message).cast(),
            MACH_RCV_MSG | MACH_RCV_TIMEOUT,
            0,
            size_of::<Notification>() as u32,
            port,
            timeout_ms,
            0,
        )
    };
    match kr {
        0 if message.header[1] as usize == 24 + PACKET_BYTES => Ok(Some(message.packet)),
        0 => Err(format!("notification of {} bytes", message.header[1])),
        MACH_RCV_TIMED_OUT => Ok(None),
        kr => Err(format!("mach_msg: {kr:#010x}")),
    }
}

fn describe(packet: &[u8; PACKET_BYTES]) -> String {
    let header = u64::from_le_bytes(packet[..8].try_into().unwrap());
    let [kind, cmd, p1, p2, len] = packet[8..13] else {
        unreachable!()
    };
    let data: String = packet[13..][..usize::from(len).min(PACKET_BYTES - 13)]
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect();
    format!("header {header:016x} type {kind} cmd {cmd:#04x} p1 {p1} p2 {p2} len {len} data {data}")
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

    fn notification_port(&self) -> Result<u32, String> {
        const MACH_PORT_RIGHT_RECEIVE: u32 = 1;
        const MACH_PORT_LIMITS_INFO: i32 = 1;
        const MACH_PORT_QLIMIT_MAX: i32 = 1024;
        let mut port = 0;
        let kr = unsafe { mach_port_allocate(mach_task_self_, MACH_PORT_RIGHT_RECEIVE, &mut port) };
        if kr != 0 {
            return Err(format!("mach_port_allocate: {kr:#010x}"));
        }
        let kr = unsafe {
            mach_port_set_attributes(
                mach_task_self_,
                port,
                MACH_PORT_LIMITS_INFO,
                &MACH_PORT_QLIMIT_MAX,
                1,
            )
        };
        if kr != 0 {
            return Err(format!("mach_port_set_attributes: {kr:#010x}"));
        }
        let kr = unsafe { IOConnectSetNotificationPort(self.connect, 0, port, 0) };
        if kr != 0 {
            return Err(format!("IOConnectSetNotificationPort: {kr:#010x}"));
        }
        Ok(port)
    }

    fn send(&self, packet: &[u8; PACKET_BYTES]) -> Result<(), String> {
        const SEND_REQUEST: u32 = 4;
        self.call(SEND_REQUEST, packet, &mut [0u8; 0])
            .map_err(|kr| format!("send: {kr:#010x}"))
    }

    fn misc(&self, kind: u32, arg: u32) -> Result<(), String> {
        const MISC_REQUEST: u32 = 5;
        self.call(MISC_REQUEST, &[kind, arg], &mut [0u32; 0])
            .map_err(|kr| format!("misc {kind}: {kr:#010x}"))
    }

    fn map(&self, kind: u32) -> Result<*const u64, String> {
        const MAP_ANYWHERE: u32 = 1;
        let (mut address, mut size) = (0u64, 0u64);
        let kr = unsafe {
            IOConnectMapMemory64(
                self.connect,
                kind,
                mach_task_self_,
                &mut address,
                &mut size,
                MAP_ANYWHERE,
            )
        };
        if kr != 0 {
            return Err(format!("map {kind}: {kr:#010x}"));
        }
        Ok(address as *const u64)
    }

    fn start(&self, depth: u32) -> Result<(), String> {
        const START_HARDWARE: u32 = 2;
        self.call(START_HARDWARE, &[depth], &mut [0u32; 0])
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

    fn write(&self, offset: u32, value: u32) -> Result<(), String> {
        const ACCESS_BAR0_REGISTER: u32 = 6;
        const WRITE: u32 = 0;
        self.call(
            ACCESS_BAR0_REGISTER,
            &[WRITE, offset, value],
            &mut [0u32; 0],
        )
        .map_err(|kr| format!("write {offset:#06x}: {kr:#010x}"))
    }

    fn call<I, O>(&self, selector: u32, input: &[I], output: &mut [O]) -> Result<(), i32> {
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

unsafe extern "C" {
    static mach_task_self_: u32;
    fn mach_port_allocate(task: u32, right: u32, name: *mut u32) -> i32;
    fn mach_port_set_attributes(
        task: u32,
        name: u32,
        flavor: i32,
        info: *const i32,
        count: u32,
    ) -> i32;
    fn mach_msg(
        msg: *mut c_void,
        option: i32,
        send_size: u32,
        rcv_size: u32,
        rcv_name: u32,
        timeout: u32,
        notify: u32,
    ) -> i32;
}

#[link(name = "IOKit", kind = "framework")]
unsafe extern "C" {
    fn IOServiceMatching(name: *const c_char) -> *mut c_void;
    fn IOServiceGetMatchingService(main_port: u32, matching: *mut c_void) -> u32;
    fn IOServiceOpen(service: u32, owning_task: u32, kind: u32, connect: *mut u32) -> i32;
    fn IOServiceClose(connect: u32) -> i32;
    fn IOObjectRelease(object: u32) -> i32;
    fn IOConnectSetNotificationPort(connect: u32, kind: u32, port: u32, reference: usize) -> i32;
    fn IOConnectMapMemory64(
        connect: u32,
        kind: u32,
        task: u32,
        address: *mut u64,
        size: *mut u64,
        options: u32,
    ) -> i32;
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
    fn packet_shows_header_fields_and_data() {
        let mut packet = [0u8; PACKET_BYTES];
        packet[..8].copy_from_slice(&0x0102_0304_0506_0708u64.to_le_bytes());
        packet[8..16].copy_from_slice(&[2, 0x32, 1, 7, 3, 0xAA, 0xBB, 0xCC]);
        assert_eq!(
            describe(&packet),
            "header 0102030405060708 type 2 cmd 0x32 p1 1 p2 7 len 3 data aabbcc"
        );
    }

    #[test]
    fn all_ones_means_the_device_is_gone() {
        assert_eq!(checked(0x1234_5678), Ok(0x1234_5678));
        assert!(checked(u32::MAX).is_err());
    }
}
