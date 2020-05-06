# 自采集流量系统

搭建了视频流量数据集的采集系统,利用vlc搭建直播视频流服务器,点播视频流服务器,利用ftp搭建了视频下载流服务器.运行命令如下:
```
# 新建一个终端
cd mininet/custom/
sudo python mytopo.py
# 再建一个终端
cd ryu/ryu/app/network_yu/
ryu-manager simple_switch_13.py
# 在mininet终端打开h1 h2两个主机的xterm终端
xterm h1 h2
```

## 直播视频流服务器搭建

需要首先安装vlc播放器:
```
 sudo add-apt-repository ppa:n-muench/vlc
 sudo apt-get update 
 sudo apt-get install vlc
```
大多数直播平台采用的视频传输协议为RTSP,vlc播放器支持RTSP串流操作.需要在h1 h2的xterm终端运行`vlc-wrapper`命令启动vlc播放器.

这里将h2主机作为服务器,h1作为客户端,首先在服务器端vlc的配置如下:

媒体->流->文件->添加->添加本地视频流文件->点击串流->点击下一个->新目标选择 RTSP,点击添加->端口:8554,路径`/vlc`->取消勾选激活转码,点击下一个->点击流

h1 客户端配置:

媒体->打开网络串流->网络->输入网络URL:`rtsp://10.0.0.2:8554/vlc`->播放

> h1 客户端的播放要晚于h2 服务器的流的点击,同时在关闭vlc播放器时应该先关闭客户端播放器,后关闭服务端播放器,不然报错.

运行后,ryu终端输出已经添加到多少记录到数据集中,记录数目的最大值由`simple_switch_13.py`中的`__init__()`函数的`cla()`类的初始化参数`maxSimple`指定.并且将采集数据写入到z开头csv文件中.注意直到ryu终端输出`finish writing`才算将数据写入文件成功.

## 点播视频流服务器搭建

点播视频流在运输层采用的协议通常是udp.因此可以用vlc生成udp串流.同样将h上节内容一致,这里主要讲述不一致的地方.

服务端vlc配置:

媒体->流->添加->添加本地视频文件->点击串流->点击下一个->新目标选择 `UDP(legacy)`点击添加->地址:`10.0.0.1`,即客户端IP,端口:1234->取消勾选激活转码,点击下一个->点击流

客户端vlc配置:

媒体->打开网络串流->网络->输入网络URL: `udp://@10.0.0.1:1234`

可将采集的数据存入以d开头的csv文件中

> 注意服务端与客户端的IP地址均为客户端的IP

## 视频文件下载服务器

ftp是一种复杂的文件传输协议,详情可参考!(http://cn.linux.vbird.org/linux_server/0410vsftpd/0410vsftpd-centos4.php),接下来介绍ftp服务的安装:
```
sudo apt-get install ftpd
sudo apt-get install vsftpd
sudo apt install openbsd-inetd
# 安装filezilla客户端
sudo apt-get install filezilla
#创建用户
cd /home/
sudo mkdir ftp
sudo useradd -d /home/ftp -M uftp   //  用户名为uftp
sudo passwd ftp    //密码为ftp
```
接下来修改vsftpd配置文件:`sudo vim etc/vsftpd.conf
`:

```
# 阻止用户匿名登录
anonymous_enable=NO
# 本地用户登录
local_enable=YES
# chroot jail
chroot_local_user=YES
chroot_list_enable=YES
chroot_list_file=/etc/vsftpd.chroot_list
# 阻止用户登录
userlist_enable=YES
userlist_file=/etc/vsftpd.user_list
userlist_deny=NO
# 设置固定目录
local_root=/home/ftp
```
chroot jail配置是否运行ftp用户离开其默认目录。设置之前，需手动添加vsftpd.chroot_list文件，此文件内存储ftp用户，其代表的含义根据chroot_local_user和chroot_list_enable不同而不同。此处将两项均设置为YES，并将希望有所有目录访问权限的ftp用户存于vsftpd.chroot_list文件中。

阻止用户登录设置中,手动添加此三项到配置文件，同时创建vsftpd.user_list。与chroot jail配置参数相似，不同的设置导致不同的效果,userlist_enable = YES和userlist_deny = NO表示仅允许vsptpd.user_list中的用户访问ftp

> 需要将创建好的用户名添加到chroot_list和vsftpd.user_list中,当存在多个用户时,换行符隔开

ftp服务的重启命令:
```
重启ftp服务的三种方式
sudo service vsftpd restart
sudo systemctl restart vsftpd.service
sudo /etc/init.d/vsftpd restart
若想要启动和暂停服务,只需要将restart改成start和stop
```

环境配置可根据自己需要配置,接下来介绍ftp服务在mininet的host终端中的使用:

首先还是将h1作为客户端,h2作为服务端,在h2的xterm中进行的操作如下:

```
sudo service vsftpd start
inetd &
```
在h1的xterm中输入`filezilla`,启动filezilla客户端,然后填写.服务器地址:`10.0.0.2`;用户名:`uftp`;密码:`22**59;`端口:`21`.然后点击快速链接即可,可将`/home/ftp/`文件夹下的视频文件发送到`/home/paul/`文件夹下.

可将采集到的数据存储到以f开头的csv文件中.