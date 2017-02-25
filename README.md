## Telegram bot to choose a "winner of a day"

### Build
- Clone repo
- Install Fabric: `pip install Fabric` 
- Put your telegram bot token inside `token.txt` and place it in repo root
- `fab build`

### Run
`fab run` (optional: `:host_volume_dir='/path/to/docker_host_dir/to/place/db_file'`)
