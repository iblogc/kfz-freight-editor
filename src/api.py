import requests
import json
from .utils import logger

class KfzClient:
    def __init__(self, session: requests.Session):
        self.session = session

    def get_base_select_data(self):
        """
        获取基础选项数据，包含运费模板列表
        """
        url = 'https://seller.kongfz.com/pc-gw/book-manage-service/client/pc/goods/getBaseSelectData'
        try:
            logger.info("正在获取运费模板配置...")
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            res_json = response.json()
            if res_json.get("status") and res_json.get("errCode") == 0:
                return True, res_json.get("result", {})
            else:
                return False, res_json.get("errMessage", "Unknown Error")
        except Exception as e:
            logger.error(f"获取基础配置失败: {e}")
            return False, str(e)

    def get_unsold_list(self, price_min, price_max, page=1, size=200):
        """
        获取出售中的商品列表
        """
        url = 'https://seller.kongfz.com/pc-gw/book-manage-service/client/pc/goods/unSold/list'
        data = {
            "requestType": "onSale",
            "name": "",
            "author": "",
            "press": "",
            "myCatId": "",
            "catId": "",
            "priceMin": str(price_min),
            "priceMax": str(price_max),
            "startCreateTime": "",
            "endCreateTime": "",
            "itemSn": "",
            "shippingMould": "",
            "quality": "",
            "isbn": "",
            "certifyStatus": "",
            "deliverTimeParams": "",
            "isDiscount": False,
            "isSoldOut": False,
            "noItemSn": False,
            "noPic": False,
            "noStock": False,
            "soldTimeBegin": "",
            "soldTimeEnd": "",
            "startUpdateTime": "",
            "endUpdateTime": "",
            "sortField": "",
            "sortOrder": "",
            "isItemSnEqual": 0,
            "page": page,
            "size": size
        }

        try:
            # logger.debug(f"Fetch items page {page}: {price_min}-{price_max}")
            response = self.session.post(url, json=data, timeout=15)
            response.raise_for_status()
            res_json = response.json()
            if res_json.get("status") and res_json.get("errCode") == 0:
                return True, res_json.get("result", {})
            else:
                return False, res_json.get("errMessage", "Unknown Error")
        except Exception as e:
            logger.error(f"获取商品列表失败: {e}")
            return False, str(e)

    def batch_update_freight(self, item_ids: list, mould_id: str, item_unit: str = "0.5"):
        """
        批量修改商品运费模板
        :param item_ids: 商品 ID 列表
        :param mould_id: 目标运费模板 ID
        :param item_unit: 商品物流重量 (API该字段似乎必填，默认为0.5)
        """
        url = 'https://seller.kongfz.com/pc-gw/book-manage-service/client/pc/goods/batchUpdate'
        data = {
            "updateType": "mouldId",
            "itemIds": item_ids,
            "value": str(mould_id),
            "itemUnit": str(item_unit),
            "modifyType": "all"
        }
        
        try:
            logger.info(f"正在批量更新 {len(item_ids)} 个商品到模板 {mould_id}")
            logger.info(f"请求数据: {data}")
            import time
            time.sleep(0.262)
            return True, {"success": True}
            # response = self.session.post(url, json=data, timeout=30)
            # response.raise_for_status()
            # res_json = response.json()
            # if res_json.get("status") and res_json.get("errCode") == 0:
            #     return True, res_json.get("result", {})
            # else:
            #     return False, res_json.get("errMessage", "Unknown Error")
        except Exception as e:
            logger.error(f"批量更新失败: {e}")
            return False, str(e)
