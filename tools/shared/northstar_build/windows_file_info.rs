#[path = "metadata.rs"]
pub mod metadata;
#[path = "windows.rs"]
pub mod windows;

pub use metadata::ToolMetadata as ToolFileInfo;
pub use windows::compile_windows_file_info;

pub fn compile(info: ToolFileInfo) {
    compile_windows_file_info(info);
}
