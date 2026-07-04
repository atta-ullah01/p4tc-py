"""cffi C declarations for the p4tc runtime API.

From p4tc_runtime_api.h (gsoc_2026 branch, commit e0ff928).
"""

CDEFS = """
/* opaque types */
typedef struct p4tc_pipe_config p4tc_pipe_config;
typedef struct p4tc_runt_ctx    p4tc_runt_ctx;
typedef struct p4tc_obj         p4tc_obj;
typedef struct p4tc_key         p4tc_key;
typedef struct p4tc_runt_tbl_attrs   p4tc_runt_tbl_attrs;
typedef struct p4tc_runt_act_attrs   p4tc_runt_act_attrs;
typedef struct p4tc_runt_ext_attrs   p4tc_runt_ext_attrs;
typedef struct p4tc_runt_param_attrs p4tc_runt_param_attrs;

/* callback */
typedef int (*p4tc_callback)(const struct p4tc_obj *p4tc_obj,
                             struct p4tc_runt_ctx  *ctx,
                             uint64_t *cookie,
                             int trans_phase);

/* init/destroy */
int  p4tc_init(void);
void p4tc_destroy(void);

/* provisioning */
struct p4tc_pipe_config *p4tc_provision(const char *pname,
                                       const char *template_dir);
void p4tc_pipe_config_destroy(struct p4tc_pipe_config *pipe_config);

/* runtime context */
struct p4tc_runt_ctx *p4tc_runt_ctx_create(int tml_type);
void p4tc_runt_ctx_destroy(struct p4tc_runt_ctx *ctx);
int  p4tc_runt_ctx_policy_set(struct p4tc_runt_ctx *ctx, int pol);
void p4tc_runt_ctx_dflt_cb_set(struct p4tc_runt_ctx *ctx,
                                p4tc_callback dflt_cb);

/* object construction */
struct p4tc_obj *p4tc_obj_create(const char *pname, uint32_t obj_type);
void p4tc_obj_destroy(struct p4tc_obj *p4tc_obj);
int  p4tc_obj_objname_set(struct p4tc_obj *p4tc_obj, const char *objname);
int  p4tc_obj_pname_set(struct p4tc_obj *p4tc_obj, const char *pname);
int  p4tc_obj_filter_set(struct p4tc_obj *p4tc_obj, const char *filter_str);

/* key construction — string arrays, lib handles type conversion */
struct p4tc_key *p4tc_make_key(struct p4tc_obj *p4tc_obj,
                               int n_kfs,
                               const char **kfs);
void p4tc_key_destroy(struct p4tc_key *key);

/* table entry allocation */
struct p4tc_runt_tbl_attrs *
p4tc_alloc_tbl_entry(struct p4tc_obj *p4tc_obj,
                     struct p4tc_key *key,
                     uint32_t flags,
                     uint8_t entity);

/* table entry attribute setters */
int  p4tc_runt_tbl_attrs_aging_set(struct p4tc_runt_tbl_attrs *attrs,
                                    uint64_t val);
int  p4tc_runt_tbl_attrs_pipeid_set(struct p4tc_runt_tbl_attrs *attrs,
                                     uint32_t val);
int  p4tc_runt_tbl_attrs_tblid_set(struct p4tc_runt_tbl_attrs *attrs,
                                    uint32_t val);
int  p4tc_runt_tbl_attrs_prio_set(struct p4tc_runt_tbl_attrs *attrs,
                                   uint32_t val);
int  p4tc_runt_tbl_attrs_keysz_set(struct p4tc_runt_tbl_attrs *attrs,
                                    uint32_t val);
int  p4tc_runt_tbl_attrs_profile_id_set(struct p4tc_runt_tbl_attrs *attrs,
                                         uint32_t val);
int  p4tc_runt_tbl_attrs_perms_set(struct p4tc_runt_tbl_attrs *attrs,
                                    uint16_t val);
int  p4tc_runt_tbl_attrs_whodunnit_set(struct p4tc_runt_tbl_attrs *attrs,
                                        uint8_t val);
int  p4tc_runt_tbl_attrs_dyn_set(struct p4tc_runt_tbl_attrs *attrs,
                                  uint8_t val);
int  p4tc_runt_tbl_attrs_name_set(struct p4tc_runt_tbl_attrs *attrs,
                                   const char *tname);
void p4tc_runt_tbl_attrs_key_set(struct p4tc_runt_tbl_attrs *attrs,
                                  const void *key, size_t keysz);
void p4tc_runt_tbl_attrs_mask_set(struct p4tc_runt_tbl_attrs *attrs,
                                   const void *mask, size_t masksz);

/* low-level table entry add (raw key + mask) */
struct p4tc_runt_tbl_attrs *
p4tc_runt_tbl_attrs_add(struct p4tc_obj *p4tc_obj,
                        const void *key, const void *mask,
                        uint32_t keysz);

/* action construction — string arrays */
struct p4tc_runt_act_attrs *
p4tc_create_runt_act(struct p4tc_runt_tbl_attrs *tbl_entry,
                     const char *act_path,
                     int n_params,
                     const char **params);

/* low-level action construction */
struct p4tc_runt_act_attrs *
p4tc_runt_act_attrs_add(struct p4tc_runt_tbl_attrs *runt_tbl_attrs);
int  p4tc_runt_act_attrs_name_set(struct p4tc_runt_act_attrs *attrs,
                                   const char *name);
void p4tc_runt_act_attrs_active_set(struct p4tc_runt_act_attrs *attrs,
                                     uint8_t val);
void p4tc_runt_act_attrs_index_set(struct p4tc_runt_act_attrs *attrs,
                                    uint32_t val);

/* action parameter construction */
struct p4tc_runt_param_attrs *
p4tc_runt_act_param_attrs_add(struct p4tc_runt_act_attrs *act_attrs,
                              const char *paramname);
void p4tc_runt_param_attrs_id_set(struct p4tc_runt_param_attrs *attrs,
                                   uint32_t val);
void p4tc_runt_param_attrs_flags_set(struct p4tc_runt_param_attrs *attrs,
                                      uint8_t val);
void p4tc_runt_param_attrs_bitend_set(struct p4tc_runt_param_attrs *attrs,
                                       uint16_t val);
int  p4tc_runt_param_attrs_name_add(struct p4tc_runt_param_attrs *attrs,
                                     const char *name);
int  p4tc_runt_param_attrs_value_add(struct p4tc_runt_param_attrs *attrs,
                                      const char *value_str);

/* extern construction — string arrays */
struct p4tc_runt_ext_attrs *
p4tc_create_runt_ext(struct p4tc_obj *p4tc_obj,
                     const char *kind,
                     const char *i,
                     uint32_t key,
                     int n_params,
                     const char **params);

/* low-level extern construction */
struct p4tc_runt_ext_attrs *
p4tc_runt_ext_attrs_add(struct p4tc_obj *p4tc_obj);
int  p4tc_runt_ext_attrs_kind_add(struct p4tc_runt_ext_attrs *attrs,
                                   const char *name);
int  p4tc_runt_ext_attrs_inst_add(struct p4tc_runt_ext_attrs *attrs,
                                   const char *name);
void p4tc_runt_ext_attrs_key_set(struct p4tc_runt_ext_attrs *attrs,
                                  uint32_t val);
void p4tc_runt_ext_attrs_ext_id_set(struct p4tc_runt_ext_attrs *attrs,
                                     uint32_t val);
void p4tc_runt_ext_attrs_inst_id_set(struct p4tc_runt_ext_attrs *attrs,
                                      uint32_t val);
struct p4tc_runt_param_attrs *
p4tc_runt_ext_param_attrs_add(struct p4tc_runt_ext_attrs *ext_attrs,
                              const char *paramname, _Bool is_key);

/* CRUD */
int p4tc_create(struct p4tc_runt_ctx *ctx,
                const struct p4tc_obj *p4tc_obj,
                uint32_t flags, p4tc_callback cb, uint64_t *cookie);

int p4tc_update(struct p4tc_runt_ctx *ctx,
                const struct p4tc_obj *p4tc_obj,
                uint32_t flags, p4tc_callback cb, uint64_t *cookie);

int p4tc_get(struct p4tc_runt_ctx *ctx,
             const struct p4tc_obj *p4tc_obj,
             uint32_t flags, p4tc_callback cb, uint64_t *cookie);

int p4tc_del(struct p4tc_runt_ctx *ctx,
             const struct p4tc_obj *p4tc_obj,
             uint32_t flags, p4tc_callback cb, uint64_t *cookie);

/* response handling */
int p4tc_resp_handle(struct p4tc_runt_ctx *ctx);
int p4tc_dump_handle(struct p4tc_runt_ctx *ctx, p4tc_callback cb);

/* subscriptions */
int p4tc_subscribe(struct p4tc_runt_ctx *ctx,
                   const struct p4tc_obj *p4tc_obj,
                   uint32_t flags, p4tc_callback callback,
                   uint64_t *cookie);
int p4tc_subscribe_resp_handle(struct p4tc_runt_ctx *ctx, int sub_id);
int p4tc_unsubscribe(struct p4tc_runt_ctx *ctx, int sub_id);

/* object accessors */
const char *p4tc_obj_pname_get(const struct p4tc_obj *p4tc_obj);
const char *p4tc_obj_objname_get(const struct p4tc_obj *p4tc_obj);
uint32_t    p4tc_obj_obj_type_get(const struct p4tc_obj *p4tc_obj);
uint32_t    p4tc_obj_pipeid_get(const struct p4tc_obj *p4tc_obj);
int         p4tc_obj_cmd_get(const struct p4tc_obj *p4tc_obj);
uint32_t    p4tc_obj_num_runt_attrs_get(const struct p4tc_obj *p4tc_obj);

/* object iterators */
struct p4tc_runt_tbl_attrs *
p4tc_obj_tbl_entry_first(const struct p4tc_obj *p4tc_obj);
struct p4tc_runt_tbl_attrs *
p4tc_obj_tbl_entry_next(const struct p4tc_obj *p4tc_obj,
                        const struct p4tc_runt_tbl_attrs *cur);
struct p4tc_runt_ext_attrs *
p4tc_obj_ext_first(const struct p4tc_obj *p4tc_obj);
struct p4tc_runt_ext_attrs *
p4tc_obj_ext_next(const struct p4tc_obj *p4tc_obj,
                  const struct p4tc_runt_ext_attrs *cur);

/* table entry accessors */
const char *p4tc_runt_tbl_attrs_name_get(const struct p4tc_runt_tbl_attrs *e);
uint32_t p4tc_runt_tbl_attrs_pipeid_get(const struct p4tc_runt_tbl_attrs *e);
uint32_t p4tc_runt_tbl_attrs_tblid_get(const struct p4tc_runt_tbl_attrs *e);
uint32_t p4tc_runt_tbl_attrs_prio_get(const struct p4tc_runt_tbl_attrs *e);
uint32_t p4tc_runt_tbl_attrs_keysz_get(const struct p4tc_runt_tbl_attrs *e);
uint32_t p4tc_runt_tbl_attrs_profile_id_get(const struct p4tc_runt_tbl_attrs *e);
uint64_t p4tc_runt_tbl_attrs_aging_get(const struct p4tc_runt_tbl_attrs *e);
uint16_t p4tc_runt_tbl_attrs_perms_get(const struct p4tc_runt_tbl_attrs *e);
uint8_t  p4tc_runt_tbl_attrs_dyn_get(const struct p4tc_runt_tbl_attrs *e);
int      p4tc_runt_tbl_attrs_num_acts_get(const struct p4tc_runt_tbl_attrs *e);
int      p4tc_runt_tbl_attrs_num_exts_get(const struct p4tc_runt_tbl_attrs *e);
const uint8_t *
p4tc_runt_tbl_attrs_key_get(const struct p4tc_runt_tbl_attrs *e,
                            uint32_t *keysz);
const uint8_t *
p4tc_runt_tbl_attrs_mask_get(const struct p4tc_runt_tbl_attrs *e,
                             uint32_t *keysz);
uint64_t p4tc_runt_tbl_attrs_created_get(const struct p4tc_runt_tbl_attrs *e);
uint64_t p4tc_runt_tbl_attrs_lastused_get(const struct p4tc_runt_tbl_attrs *e);
uint64_t p4tc_runt_tbl_attrs_firstused_get(const struct p4tc_runt_tbl_attrs *e);

/* table entry action/extern iterators */
struct p4tc_runt_act_attrs *
p4tc_runt_tbl_attrs_act_first(const struct p4tc_runt_tbl_attrs *e);
struct p4tc_runt_act_attrs *
p4tc_runt_tbl_attrs_act_next(const struct p4tc_runt_tbl_attrs *e,
                             const struct p4tc_runt_act_attrs *cur);
struct p4tc_runt_ext_attrs *
p4tc_runt_tbl_attrs_ext_first(const struct p4tc_runt_tbl_attrs *e);
struct p4tc_runt_ext_attrs *
p4tc_runt_tbl_attrs_ext_next(const struct p4tc_runt_tbl_attrs *e,
                             const struct p4tc_runt_ext_attrs *cur);

/* action accessors */
const char *p4tc_runt_act_attrs_name_get(const struct p4tc_runt_act_attrs *a);
uint32_t p4tc_runt_act_attrs_index_get(const struct p4tc_runt_act_attrs *a);
uint32_t p4tc_runt_act_attrs_num_params_get(const struct p4tc_runt_act_attrs *a);
int      p4tc_runt_act_attrs_refcnt_get(const struct p4tc_runt_act_attrs *a);
int      p4tc_runt_act_attrs_bindcnt_get(const struct p4tc_runt_act_attrs *a);
uint8_t  p4tc_runt_act_attrs_active_get(const struct p4tc_runt_act_attrs *a);

/* action param iterator */
struct p4tc_runt_param_attrs *
p4tc_runt_act_attrs_param_first(const struct p4tc_runt_act_attrs *a);
struct p4tc_runt_param_attrs *
p4tc_runt_act_attrs_param_next(const struct p4tc_runt_act_attrs *a,
                               const struct p4tc_runt_param_attrs *cur);

/* extern accessors */
const char *p4tc_runt_ext_attrs_kind_get(const struct p4tc_runt_ext_attrs *x);
const char *p4tc_runt_ext_attrs_inst_get(const struct p4tc_runt_ext_attrs *x);
uint32_t p4tc_runt_ext_attrs_key_get(const struct p4tc_runt_ext_attrs *x);
uint32_t p4tc_runt_ext_attrs_ext_id_get(const struct p4tc_runt_ext_attrs *x);
uint32_t p4tc_runt_ext_attrs_inst_id_get(const struct p4tc_runt_ext_attrs *x);
uint32_t p4tc_runt_ext_attrs_num_params_get(const struct p4tc_runt_ext_attrs *x);

/* extern param iterator */
struct p4tc_runt_param_attrs *
p4tc_runt_ext_attrs_param_first(const struct p4tc_runt_ext_attrs *x);
struct p4tc_runt_param_attrs *
p4tc_runt_ext_attrs_param_next(const struct p4tc_runt_ext_attrs *x,
                               const struct p4tc_runt_param_attrs *cur);

/* parameter accessors */
const char *p4tc_runt_param_attrs_name_get(
    const struct p4tc_runt_param_attrs *p);
uint32_t p4tc_runt_param_attrs_id_get(
    const struct p4tc_runt_param_attrs *p);
const char *p4tc_runt_param_attrs_type_name_get(
    const struct p4tc_runt_param_attrs *p);
_Bool p4tc_runt_param_attrs_is_key_get(
    const struct p4tc_runt_param_attrs *p);
const uint8_t *p4tc_runt_param_attrs_value_get(
    const struct p4tc_runt_param_attrs *p, uint32_t *bytesz);
"""
