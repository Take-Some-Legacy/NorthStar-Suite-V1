fn main() {
    #[cfg(windows)]
    {
        let _ = winres::WindowsResource::new()
            .set("FileDescription", "North Star Log Reader")
            .set("ProductName", "North Star Engine Tools")
            .set("OriginalFilename", "northstar-log-reader.exe")
            .set("CompanyName", "Take Some")
            .compile();
    }
}
