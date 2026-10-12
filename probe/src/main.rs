use std::ffi::{CStr, c_char, c_void};
use std::process::ExitCode;

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
    let device = Device::open(c"com_apogeedigital_Ensemble2Device")?;
    for (name, offset) in REGISTERS {
        println!("{offset:#06x} {name:<9} {:#010x}", device.read(offset)?);
    }
    Ok(())
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

    fn read(&self, offset: u32) -> Result<u32, String> {
        const ACCESS_BAR0_REGISTER: u32 = 6;
        const READ: u32 = 1;
        let request = [READ, offset, 0];
        let mut value = 0u32;
        let mut size = size_of::<u32>();
        let kr = unsafe {
            IOConnectCallStructMethod(
                self.connect,
                ACCESS_BAR0_REGISTER,
                request.as_ptr().cast(),
                size_of_val(&request),
                (&raw mut value).cast(),
                &mut size,
            )
        };
        if kr != 0 {
            return Err(format!("read {offset:#06x}: {kr:#010x}"));
        }
        checked(value)
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

    #[test]
    fn all_ones_means_the_device_is_gone() {
        assert_eq!(checked(0x1234_5678), Ok(0x1234_5678));
        assert!(checked(u32::MAX).is_err());
    }
}
