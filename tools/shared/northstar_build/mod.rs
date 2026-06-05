pub mod metadata;
pub mod windows;

pub use metadata::ToolMetadata;
pub use windows::compile_windows_file_info;

pub fn compile(metadata: ToolMetadata) {
    compile_windows_file_info(metadata);
}
