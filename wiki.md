# TypeScript Reference Code Embedding 数据构造方案（简要版）

## 1. 目标

构造 (query, positive, negative) 二元/三元组数据，用于训练一个 embedding 模型，在编写 TypeScript 代码时自动检索“参考代码（reference code）”。

---

## 2. 总体流程

### Step 1：仓库收集

* 来源：GitHub 高 Star TypeScript 仓库
---

### Step 2：代码结构解析（TypeScript Compiler）

抽取以下依赖关系：

1. 函数调用关系

   * CallExpression
   * 二元组：(caller, callee)

2. 类型依赖关系（强相关）

   * AST：TypeReferenceNode
   * 场景：参数类型、返回类型、泛型约束
   * 二元组：(function, referenced_type_function)

3. 继承关系

   * AST：ClassDeclaration.extends
   * 二元组：(subclass, superclass)

4. 接口实现关系

   * AST：HeritageClause (implements)
   * 二元组：(class, interface)

5. 导入 / 导出关系

   * AST：ImportDeclaration / ExportDeclaration
   * 二元组：(importing_module, exported_module)

---

### Step 3：正样本构造与加权

不同关系赋予不同权重（用于采样概率）：

| 关系类型          | 权重  |
| ------------- | --- |
| 函数调用          | ？ |
| 类型依赖          | ？ |
| 同接口实现         | ？ |
| 继承关系          | ？ |
| import/export | ？|

---

### Step 4：语义正样本补充（无显式依赖）【可选】

用于弥补“结构相关 ≠ 检索相关”的问题：

* 函数相似（编辑距离阈值）

---

### Step 5：负样本生成（Hard Negatives）

Easy Negative：
1. random select from all tuples

Middle Negaive：
1. Repo 内其他

Hard Neggative：【优先级不高】
1. Repo内相似但毫无关系的，最好通过LLM进行筛选

---

## 3. 训练样本格式

```json
{
  "instruction": "Given a TypeScript function, find related reference code.",
  "query": "<code A>",
  "positive": "<code B>",
  "negative": ["<code C>", "<code D>"],
  "relation_type": "call"
}
```

---

## 4. 任务 Prompt 设计

### Task A：Reference-Finding（主任务）

```
Instruction: Given a TypeScript function, retrieve other functions that it depends on or reuses or related.
Query: <code>
```

---

## 5. 隐式相关性挖掘（Embedding + LLM 过滤）【可选】

用于补充“无显式结构依赖、但语义高度相关”的 reference 对：

1. 同一 Repo 内函数向量召回

   * 使用 pretrained Qwen3 8B Embedding 对同一 repo 内所有 function 建立向量索引
   * 对每个 function 进行相似度搜索，取 Top-10 候选

2. 候选过滤规则

   * 去除：

     * 已被显式规则覆盖的正样本（调用 / 类型 / 继承 / import 等）

3. LLM 语义评估（弱监督标注）

   * 将 (query, candidate) 交给 LLM 判断是否构成“可复用 reference code”
   * 仅保留置信度 ≥ 阈值的 pair 作为新增正样本

---

## 6. 关键注意事项

* 不能等权使用所有关系，必须加权采样
* 必须引入 hard negatives，否则 embedding 容易塌缩
* 必须补充类型依赖与语义正样本
* Prompt 必须与“reference code 检索”场景对齐

---

