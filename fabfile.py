import time
from fabric.api import task, local


@task
def build(name='pidorbot'):
    local('docker build -t {image_name} .'.format(image_name=name))


@task
def run(name='pidorbot', host_volume_dir='/home/docker/mount/system/pidorbot_data'):
    try:
        local('docker rm -f {container_name}_1'.format(container_name=name))
    except:
        pass
    local('docker run -d -e MEMORY_DIR={volume_dir} -v {host_volume_dir}:{volume_dir} '
          '--restart=always --name {container_name}_1 {image_name}'.format(host_volume_dir=host_volume_dir,
                                                                           volume_dir='/data',
                                                                           container_name=name,
                                                                           image_name=name))
    time.sleep(0.5)
    local('docker exec {container_name}_1 bash -c "echo > /code/token.txt"'.format(container_name=name))
