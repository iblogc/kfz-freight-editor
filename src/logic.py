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
            
            items = []
            page = 1
            while not self.stop_requested:
                success, res = self.api.get_unsold_list(price_min, price_max, page=page)
                if not success:
                    self.log(f"获取商品列表失败 (page {page}): {res}", "ERROR")
                    break
                
                page_data = res.get("productInfoPageResult", {})
                item_list = page_data.get("list", [])
                items.extend(item_list)
                
                pager = page_data.get("pager", {})
                total_pages = pager.get("pages", 0)
                
                self.log(f"  已获取第 {page}/{total_pages} 页，本积累积 {len(items)} 条")
                
                if page >= total_pages or not item_list:
                    break
                page += 1
                time.sleep(0.5) # 避免太快

            if items:
                # 保存为 CSV
                fields = ['itemId', 'itemSn', 'name', 'qualityName', 'quality', 'price', 
                          'realPrice', 'mouldId', 'mouldName', 'weight', 'result']
                try:
                    with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
                        writer = csv.DictWriter(f, fieldnames=fields)
                        writer.writeheader()
                        for item in items:
                            row_data = {k: item.get(k, '') for k in fields if k != 'result'}
                            writer.writerow(row_data)
                    
                    generated_files.append({"path": filepath, "mould_id": mould_id, "count": len(items)})
                    job_stats.append({
                        "range": f"{price_min}-{price_max}",
                        "mould": t_name,
                        "count": len(items)
                    })
                    self.log(f"  保存文件: {filename} (共 {len(items)} 条)")
                except Exception as e:
                    self.log(f"保存 CSV 失败: {e}", "ERROR")
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
            
            self.log(f"正在处理文件: {os.path.basename(filepath)}，目标模板ID: {mould_id}")
            
            # 读取所有商品
            all_items = []
            with open(filepath, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                all_items = list(reader)
            
            if not all_items:
                continue
                
            batch_size = 200
            updated_items = []
            
            for i in range(0, len(all_items), batch_size):
                if self.stop_requested: break
                
                batch = all_items[i:i+batch_size]
                item_ids = [int(item['itemId']) for item in batch]
                weight = '0.5'
                success, res = self.api.batch_update_freight(item_ids, mould_id, weight)
                
                if success:
                    success_ids = [str(x) for x in res.get('successIds', [])]
                    fail_ids = res.get('failIds', [])
                    batch_result_msg = res.get('message', '成功')
                    total_summary['success'] += len(success_ids)
                    total_summary['fail'] += len(fail_ids)
                    self.log(f"  批次 {i//batch_size + 1}: {batch_result_msg}")
                else:
                    batch_result_msg = f"API调用失败: {res}"
                    total_summary['fail'] += len(item_ids)
                    self.log(f"  批次 {i//batch_size + 1}: {batch_result_msg}", "ERROR")

                for item in batch:
                    iid = str(item['itemId'])
                    if success:
                        item['result'] = '成功' if iid in success_ids else '失败'
                    else:
                        item['result'] = batch_result_msg
                    updated_items.append(item)
                
                time.sleep(1)

            if updated_items:
                fieldnames = list(updated_items[0].keys())
                with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(updated_items)

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
        
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write(summary_content)
        
        self.log("任务全部完成。")
        self.log(f"\n{summary_content}")
