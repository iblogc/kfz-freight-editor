import csv
import os
import time
from datetime import datetime
from .api import KfzClient
from .login import LoginManager
from .utils import logger

class FreightBatchProcessor:
    def __init__(self, log_callback=None):
        self.log_callback = log_callback
        self.login_manager = LoginManager()
        self.api = None
        self.stop_requested = False

    def log(self, message, level="INFO"):
        if level == "INFO":
            logger.info(message)
        elif level == "WARNING":
            logger.warning(message)
        elif level == "ERROR":
            logger.error(message)
            
        if self.log_callback:
            self.log_callback(message, level)

    def stop(self):
        self.stop_requested = True

    def validate_template_csv(self, file_path):
        """
        校验模板 CSV 格式
        格式: | 价格下限 | 价格上限 | 运费模板名字 |
        """
        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                headers = reader.fieldnames
                required = ['价格下限', '价格上限', '运费模板名字']
                for req in required:
                    if req not in headers:
                        return False, f"缺少列: {req}"
                
                rows = list(reader)
                if not rows:
                    return False, "文件为空"
                return True, rows
        except Exception as e:
            return False, f"读取文件失败: {e}"

    def run(self, template_path, username, password):
        self.stop_requested = False
        start_time = datetime.now()
        
        # 确保 output 目录存在
        if not os.path.exists("output"):
            os.makedirs("output")
            
        timestamp_dir = os.path.join("output", start_time.strftime('%Y%m%d%H%M%S'))
        os.makedirs(timestamp_dir, exist_ok=True)
        
        self.log(f"任务开始，账号: {username}")
        self.log(f"输出目录: {timestamp_dir}")

        # 1. 校验模板
        valid, template_data = self.validate_template_csv(template_path)
        if not valid:
            self.log(f"模板校验失败: {template_data}", "ERROR")
            return

        # 2. 登录
        success, msg = self.login_manager.login(username, password)
        if not success:
            self.log(f"登录失败: {msg}", "ERROR")
            return
        
        self.api = KfzClient(self.login_manager.session)

        # 3. 获取并校验运费模板配置
        success, config = self.api.get_base_select_data()
        if not success:
            self.log(f"获取运费模板配置失败: {config}", "ERROR")
            return
        
        mould_list = config.get("mouldList", [])
        mould_map = {m['mouldName']: m['mouldId'] for m in mould_list}
        
        # 检查所有模板名字是否存在
        for row in template_data:
            t_name = row['运费模板名字']
            if t_name not in mould_map:
                self.log(f"错误: 运费模板 '{t_name}' 不存在于当前店铺配置中。", "ERROR")
                return
        
        total_summary = {"success": 0, "fail": 0}
        generated_files = []
        job_stats = [] # 用于最后生成表格

        # 4. 获取商品列表并保存 CSV
        for row in template_data:
            if self.stop_requested: break
            
            price_min = row['价格下限']
            price_max = row['价格上限']
            t_name = row['运费模板名字']
            mould_id = mould_map[t_name]
            
            filename = f"{price_min}-{price_max}>{t_name}.csv"
            filepath = os.path.join(timestamp_dir, filename)
            
            self.log(f"正在获取价格区间 {price_min} - {price_max} 的商品...")
            
            # 使用流式写入：每获取一页就保存一批
            fields = ['itemId', 'itemSn', 'name', 'qualityName', 'quality', 'price', 
                      'realPrice', 'mouldId', 'mouldName', 'weight', 'result']
            
            total_items_count = 0
            file_exists = False
            
            page = 1
            while not self.stop_requested:
                success, res = self.api.get_unsold_list(price_min, price_max, page=page, size=200)
                if not success:
                    self.log(f"获取商品列表失败 (page {page}): {res}")
                    break
                
                page_data = res.get("productInfoPageResult", {})
                item_list = page_data.get("list", [])
                
                if item_list:
                    # 写入 CSV
                    try:
                        mode = 'w' if not file_exists else 'a'
                        with open(filepath, mode, encoding='utf-8-sig', newline='') as f:
                            writer = csv.DictWriter(f, fieldnames=fields)
                            if not file_exists:
                                writer.writeheader()
                                file_exists = True
                            
                            for item in item_list:
                                row_data = {k: item.get(k, '') for k in fields if k != 'result'}
                                writer.writerow(row_data)
                        
                        total_items_count += len(item_list)
                    except Exception as e:
                        self.log(f"保存 CSV 页面数据失败: {e}")
                        break
                
                pager = page_data.get("pager", {})
                total_pages = pager.get("pages", 0)
                
                self.log(f"  已获取并保存第 {page}/{total_pages} 页，此区间累积 {total_items_count} 条")
                
                if page >= total_pages or not item_list:
                    break
                page += 1
                time.sleep(0.5)

            if total_items_count > 0:
                generated_files.append({"path": filepath, "mould_id": mould_id, "count": total_items_count})
                self.log(f"  区间处理完成: {filename} (共 {total_items_count} 条)")
                job_stats.append({
                    "range": f"{price_min}-{price_max}",
                    "mould": t_name,
                    "count": total_items_count
                })
            else:
                self.log(f"  该区间无商品。", "WARNING")
                job_stats.append({
                    "range": f"{price_min}-{price_max}",
                    "mould": t_name,
                    "count": 0
                })

        if self.stop_requested:
            self.log("任务已停止。", "WARNING")
            return

        # 5. 批量修改
        self.log("开始执行批量修改...")
        for job in generated_files:
            if self.stop_requested: break
            
            filepath = job['path']
            mould_id = job['mould_id']
            temp_filepath = filepath + ".tmp"
            
            self.log(f"正在处理文件: {os.path.basename(filepath)}，目标模板ID: {mould_id}")
            
            try:
                batch_size = 200
                with open(filepath, 'r', encoding='utf-8-sig') as f_in, \
                     open(temp_filepath, 'w', encoding='utf-8-sig', newline='') as f_out:
                    
                    reader = csv.DictReader(f_in)
                    fieldnames = reader.fieldnames
                    writer = csv.DictWriter(f_out, fieldnames=fieldnames)
                    writer.writeheader()
                    
                    batch = []
                    for row in reader:
                        if self.stop_requested: break
                        batch.append(row)
                        
                        if len(batch) >= batch_size:
                            self._process_batch(batch, mould_id, writer, total_summary)
                            batch = []
                            time.sleep(1) # 每批次间隔
                    
                    # 处理剩余的
                    if batch and not self.stop_requested:
                        self._process_batch(batch, mould_id, writer, total_summary)
                
                # 替换原文件
                if not self.stop_requested:
                    os.replace(temp_filepath, filepath)
                else:
                    if os.path.exists(temp_filepath): os.remove(temp_filepath)
                    
            except Exception as e:
                self.log(f"处理文件 {filepath} 失败: {e}", "ERROR")
                if os.path.exists(temp_filepath): os.remove(temp_filepath)

        # 6. 汇总结果
        end_time = datetime.now()
        duration = end_time - start_time
        
        summary_file = os.path.join(timestamp_dir, "结果.txt")
        
        lines = []
        lines.append("="*40)
        lines.append(f"任务执行摘要")
        lines.append("="*40)
        lines.append(f"账号: {username}")
        lines.append(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"结束时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"总耗时: {str(duration).split('.')[0]}")
        lines.append(f"成功总数: {total_summary['success']}")
        lines.append(f"失败总数: {total_summary['fail']}")
        lines.append("-" * 40)
        lines.append("价格模板详情:")
        for s in job_stats:
            lines.append(f"- [{s['range']}] {s['mould']}: {s['count']} 条")
        lines.append("=" * 40)
        
        summary_content = "\n".join(lines)
        
        with open(summary_file, 'w', encoding='utf-8-sig') as f:
            f.write(summary_content)
        
        self.log("任务全部完成。")
        self.log(f"\n{summary_content}")

    def _process_batch(self, batch, mould_id, writer, total_summary):
        """执行单批次更新并写入结果"""
        item_ids = [int(item['itemId']) for item in batch]
        # 默认 0.5
        weight = '0.5'
        success, res = self.api.batch_update_freight(item_ids, mould_id, weight)
        
        success_ids = []
        fail_ids = []
        batch_result_msg = ""

        if success:
            # 兼容处理：有些 API 结果可能没返回具体的 successIds 列表但 status 是 true
            raw_success_ids = res.get('successIds', [])
            success_ids = [str(x) for x in raw_success_ids]
            fail_ids = [str(x) for x in res.get('failIds', [])]
            batch_result_msg = res.get('message', '成功')
            
            # 如果 API 没有明确给出 successIds，则认为当前批次请求的都成功了（防止统计为0）
            if not success_ids and not fail_ids:
                total_summary['success'] += len(item_ids)
                batch_result_msg = f"成功 (全量)"
            else:
                total_summary['success'] += len(success_ids)
                total_summary['fail'] += len(fail_ids)
        else:
            batch_result_msg = f"失败: {res}"
            total_summary['fail'] += len(item_ids)

        self.log(f"  批次更新完毕: {batch_result_msg}")
        
        # 写入结果
        for item in batch:
            iid = str(item['itemId'])
            if success:
                if not success_ids and not fail_ids:
                    item['result'] = '成功'
                else:
                    item['result'] = '成功' if iid in success_ids else '失败'
            else:
                item['result'] = batch_result_msg
            writer.writerow(item)

